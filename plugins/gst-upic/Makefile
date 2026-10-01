# GStreamer UPIC Plugin Makefile

# Plugin name
PLUGIN_NAME = gstupic
PLUGIN_LIB = libgstupic.so
VERSION = 1.0

# Installation paths
GST_PLUGIN_PATH ?= /usr/local/lib/gstreamer-1.0
GST_SCANNER = gst-inspect-1.0

# Compiler and flags
CC = gcc
CFLAGS = -Wall -O2 -fPIC \
	$(shell pkg-config --cflags gstreamer-1.0 gstreamer-base-1.0) \
	-DGST_PACKAGE_NAME=\"VisualAudio\" \
	-DGST_PACKAGE_ORIGIN=\"https://github.com/tdw419/visual_audio\" \
	-DVERSION=\"$(VERSION)\"

LDFLAGS = -shared \
	$(shell pkg-config --libs gstreamer-1.0 gstreamer-base-1.0) \
	-ljson-c

# Source files
SOURCES = gstupic.c
OBJECTS = $(SOURCES:.c=.o)

# Default target
all: $(PLUGIN_LIB)

# Build plugin
$(PLUGIN_LIB): $(OBJECTS)
	$(CC) $(LDFLAGS) -o $@ $^
	@echo "Plugin built: $(PLUGIN_LIB)"

# Compile source files
%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Install plugin
install: $(PLUGIN_LIB)
	@echo "Installing plugin to $(GST_PLUGIN_PATH)..."
	install -d $(GST_PLUGIN_PATH)
	install -m 644 $(PLUGIN_LIB) $(GST_PLUGIN_PATH)/
	@echo "Plugin installed. Run 'gst-inspect-1.0 upicdec' to verify."

# Uninstall plugin
uninstall:
	@echo "Uninstalling plugin..."
	rm -f $(GST_PLUGIN_PATH)/$(PLUGIN_LIB)
	@echo "Plugin uninstalled."

# Test plugin
test: install
	@echo "Testing plugin..."
	$(GST_SCANNER) upicdec

# Clean build artifacts
clean:
	rm -f $(OBJECTS) $(PLUGIN_LIB)
	@echo "Cleaned build artifacts."

# Rebuild everything
rebuild: clean all

# Show help
help:
	@echo "Visual Audio GStreamer Plugin Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all       - Build plugin (default)"
	@echo "  install   - Install plugin to system"
	@echo "  uninstall - Remove plugin from system"
	@echo "  test      - Build and test plugin"
	@echo "  clean     - Remove build artifacts"
	@echo "  rebuild   - Clean and rebuild"
	@echo "  help      - Show this help message"
	@echo ""
	@echo "Environment variables:"
	@echo "  GST_PLUGIN_PATH - Installation path (default: /usr/local/lib/gstreamer-1.0)"

.PHONY: all install uninstall test clean rebuild help