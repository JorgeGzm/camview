PY        := python3
VENV      := .venv
BIN       := $(VENV)/bin
STAMP     := $(VENV)/.installed
WHEEL     := dist/camview-*.whl
SYS_DEPS  := python3-gi gir1.2-gtk-3.0 gir1.2-gstreamer-1.0 \
             gstreamer1.0-plugins-base gstreamer1.0-plugins-good v4l-utils

# O typelib GstVideo (pacote gir1.2-gst-plugins-base-1.0) é necessário em
# runtime. Se não estiver instalado no sistema, uma cópia local é baixada
# para o venv via apt-get download (não requer sudo).
GIR_PKG   := gir1.2-gst-plugins-base-1.0
GIR_DIR   := $(VENV)/girepository
GIR_STAMP := $(VENV)/.typelibs-ok

# O elemento coloreffects (presets sepia/cross-process dos filtros) vem do
# gstreamer1.0-plugins-bad. Se não estiver instalado, uma cópia local do
# plugin é baixada para o venv (sem sudo); sem ele os demais filtros seguem
# funcionando.
BAD_PKG   := gstreamer1.0-plugins-bad
GST_DIR   := $(VENV)/gstplugins
GST_STAMP := $(VENV)/.gstplugins-ok
RUN_ENV   := GI_TYPELIB_PATH=$(GIR_DIR) GST_PLUGIN_PATH=$(GST_DIR)

.PHONY: help setup venv build run debug install delete test lint format clean desktop appimage deb

help:
	@echo "camview task runner:"
	@echo "  make setup    - check system dependencies and create the development venv"
	@echo "  make build    - build the wheel into dist/"
	@echo "  make appimage - build the release AppImage into releases/"
	@echo "  make deb      - build the release .deb into releases/"
	@echo "  make run      - run from the venv (ARGS='...' for options)"
	@echo "  make debug    - run with verbose GStreamer logging (GST_DEBUG)"
	@echo "  make install  - install camview for the user through pipx (global command)"
	@echo "  make delete   - uninstall camview from the system (pipx uninstall)"
	@echo "  make test     - run the unit tests (pytest)"
	@echo "  make lint     - static analysis (ruff)"
	@echo "  make format   - format the code (ruff format)"
	@echo "  make clean    - remove venv, dist/ and caches"

# ---------------------------------------------------------------- setup ----

setup:
	@missing=""; \
	for pkg in $(SYS_DEPS); do \
		dpkg -s $$pkg >/dev/null 2>&1 || missing="$$missing $$pkg"; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "Missing system dependencies. Install them with:"; \
		echo "  sudo apt install$$missing"; \
		exit 1; \
	fi
	@echo "System dependencies OK."
	$(MAKE) venv $(GIR_STAMP) $(GST_STAMP) desktop

$(STAMP): pyproject.toml
	$(PY) -m venv --system-site-packages $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev]"
	touch $(STAMP)

venv: $(STAMP)

$(GIR_STAMP): | $(STAMP)
	@if ls /usr/lib/*/girepository-1.0/GstVideo-1.0.typelib >/dev/null 2>&1; then \
		echo "System GstVideo typelib OK."; \
	else \
		echo "$(GIR_PKG) not installed, downloading a local copy into the venv (no sudo)..."; \
		rm -rf $(VENV)/gir-tmp && mkdir -p $(VENV)/gir-tmp $(GIR_DIR) && \
		( cd $(VENV)/gir-tmp && apt-get download $(GIR_PKG) && \
		  dpkg -x $(GIR_PKG)*.deb x ) && \
		find $(VENV)/gir-tmp/x -name '*.typelib' -exec cp {} $(GIR_DIR)/ \; && \
		rm -rf $(VENV)/gir-tmp && \
		echo "For a permanent install: sudo apt install $(GIR_PKG)"; \
	fi
	@test -f $(GIR_DIR)/GstVideo-1.0.typelib || \
		ls /usr/lib/*/girepository-1.0/GstVideo-1.0.typelib >/dev/null 2>&1
	@touch $(GIR_STAMP)

$(GST_STAMP): | $(STAMP)
	@if ls /usr/lib/*/gstreamer-1.0/libgstcoloreffects.so >/dev/null 2>&1; then \
		echo "System coloreffects plugin OK."; \
	else \
		echo "$(BAD_PKG) not installed, downloading the coloreffects plugin (no sudo)..."; \
		rm -rf $(VENV)/gst-tmp && mkdir -p $(VENV)/gst-tmp $(GST_DIR) && \
		( cd $(VENV)/gst-tmp && apt-get download $(BAD_PKG) && \
		  dpkg -x $(BAD_PKG)*.deb x ) && \
		find $(VENV)/gst-tmp/x -name 'libgstcoloreffects.so' \
		     -exec cp {} $(GST_DIR)/ \; && \
		rm -rf $(VENV)/gst-tmp && \
		echo "For a permanent install: sudo apt install $(BAD_PKG)"; \
	fi
	@touch $(GST_STAMP)

# ------------------------------------------------------- build / install ----

build: $(STAMP)
	rm -rf dist
	$(BIN)/python -m build --wheel
	@echo "Wheel built into dist/."

THEME_DIR    := $(HOME)/.local/share/icons/hicolor
ICON_DEST    := $(THEME_DIR)/scalable/apps/camview.svg
DESKTOP_DEST := $(HOME)/.local/share/applications/camview.desktop

# Integração com o desktop (ícone no dock/menu). O GNOME identifica a janela
# pelo WM_CLASS e busca o camview.desktop — necessário mesmo sem `make install`.
desktop:
	mkdir -p $(dir $(ICON_DEST)) $(dir $(DESKTOP_DEST))
	cp src/camview/assets/icon.svg $(ICON_DEST)
	cp src/camview/assets/camview.desktop $(DESKTOP_DEST)
# O gtk-update-icon-cache exige um index.theme no diretório do tema. Sem ele
# respondia "No theme index file" e não atualizava nada — silenciosamente,
# porque a linha é tolerante a falha (-).
	@test -f $(THEME_DIR)/index.theme || cp /usr/share/icons/hicolor/index.theme \
		$(THEME_DIR)/index.theme 2>/dev/null || true
	-gtk-update-icon-cache -q -f -t $(THEME_DIR) 2>/dev/null
	-update-desktop-database -q $(HOME)/.local/share/applications 2>/dev/null
	@echo "Icon and desktop entry installed."
	@echo "If the dock still shows the old icon: GNOME Shell keeps the app icon"
	@echo "in memory for the whole session. Press Alt+F2, type 'r', Enter."

appimage: build
	bash scripts/build-appimage.sh

deb: build
	bash scripts/build-deb.sh

install: build desktop
	@dpkg -s $(GIR_PKG) >/dev/null 2>&1 || { \
		echo "A global install requires the system package:"; \
		echo "  sudo apt install $(GIR_PKG)"; \
		exit 1; }
	pipx install --force --system-site-packages $(WHEEL)
	@echo "Installed. Run it with: camview (also in the applications menu)"

delete:
	pipx uninstall camview || true
	rm -f $(ICON_DEST) $(DESKTOP_DEST)
	-gtk-update-icon-cache -q $(HOME)/.local/share/icons/hicolor 2>/dev/null
	-update-desktop-database -q $(HOME)/.local/share/applications 2>/dev/null

# ------------------------------------------------------------ run / debug ----

run: $(STAMP) $(GIR_STAMP) $(GST_STAMP)
	$(RUN_ENV) $(BIN)/camview $(ARGS)

debug: $(STAMP) $(GIR_STAMP) $(GST_STAMP)
	$(RUN_ENV) GST_DEBUG=3,v4l2src:5 G_MESSAGES_DEBUG=all $(BIN)/camview $(ARGS)

# --------------------------------------------------------------- qualidade ----

test: $(STAMP)
	$(BIN)/pytest

lint: $(STAMP)
	$(BIN)/ruff check src tests

format: $(STAMP)
	$(BIN)/ruff format src tests

# ------------------------------------------------------------------ clean ----

clean:
	rm -rf $(VENV) build dist src/*.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
