#!/usr/bin/env bash
# build_avl352_mac.sh — Build AVL 3.52 for macOS (development debugging ONLY)
#
# This binary is for LOCAL DEVELOPMENT TESTING ONLY.
# Production code MUST use avl352.exe (Windows). See CLAUDE.md.
#
# Prerequisites: Homebrew, gfortran (installed via gcc)
# Optional: XQuartz (for full X11 graphics support)
#
# Usage: ./build_avl352_mac.sh
# Output: friend files/avl352_mac

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="$PROJECT_DIR/friend files/avl352_mac"
AVL_URL="https://web.mit.edu/drela/Public/web/avl/avl3.52.tgz"
# The source tarball extracts to this directory name
AVL_SRCDIR_NAME="AVL3.52rel09032025"

BUILDDIR=""
cleanup() {
    if [[ -n "$BUILDDIR" && -d "$BUILDDIR" ]]; then
        rm -rf "$BUILDDIR"
    fi
}
trap cleanup EXIT

echo "=== AVL 3.52 macOS Build Script ==="
echo "Output: $OUTPUT"
echo ""

# ── 1. Preflight checks ──────────────────────────────────────────────
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: This script is for macOS only."
    exit 1
fi

if ! command -v brew &>/dev/null; then
    echo "ERROR: Homebrew is required. Install from https://brew.sh"
    exit 1
fi

# Check/install gfortran (comes with gcc)
if ! command -v gfortran &>/dev/null; then
    echo "Installing gfortran (via gcc)..."
    brew install gcc
fi

GFORTRAN="$(command -v gfortran)"
echo "Using gfortran: $GFORTRAN"
$GFORTRAN --version | head -1

# ── 2. Detect X11 / XQuartz ──────────────────────────────────────────
USE_STUBS=false
if [[ -f /opt/X11/include/X11/Xlib.h ]]; then
    echo "XQuartz detected at /opt/X11/"
else
    echo ""
    echo "XQuartz not found. It provides X11 libraries needed to compile"
    echo "AVL's graphics code. Since this app runs headless (PLOP G F),"
    echo "we can compile without it using stub functions."
    echo ""
    read -rp "Install XQuartz via Homebrew? [y/N] " answer
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
        echo "Installing XQuartz..."
        brew install --cask xquartz
        if [[ ! -f /opt/X11/include/X11/Xlib.h ]]; then
            echo "WARNING: XQuartz installed but X11 headers not found."
            echo "You may need to restart your terminal or reboot."
            echo "Falling back to stub mode."
            USE_STUBS=true
        fi
    else
        echo "Proceeding without XQuartz (stub mode)."
        USE_STUBS=true
    fi
fi

# ── 3. Download & extract AVL 3.52 source ────────────────────────────
BUILDDIR="$(mktemp -d)"
echo ""
echo "Downloading AVL 3.52 source..."
curl -sL "$AVL_URL" -o "$BUILDDIR/avl3.52.tgz"
echo "Extracting..."
tar xzf "$BUILDDIR/avl3.52.tgz" -C "$BUILDDIR"

AVLSRC="$BUILDDIR/$AVL_SRCDIR_NAME"
if [[ ! -d "$AVLSRC" ]]; then
    echo "ERROR: Expected source directory $AVL_SRCDIR_NAME not found."
    echo "Contents of build dir:"
    ls "$BUILDDIR"
    exit 1
fi
echo "Source extracted to $AVLSRC"

# ── 4. Build plotlib (libPlt_gDP.a) ──────────────────────────────────
echo ""
echo "Building plotlib..."
cd "$AVLSRC/plotlib"

# Use the gfortranDP config as base
cp config.make.gfortranDP config.make

if [[ "$USE_STUBS" == true ]]; then
    # Create a no-op stub for Xwin2.c (no X11 needed)
    cat > "$AVLSRC/plotlib/Xwin2_stub.c" << 'STUBEOF'
/* Xwin2_stub.c — No-op stubs for AVL plotlib X11 interface.
 * Used when compiling without XQuartz (headless mode only).
 * Must be compiled with -DUNDERSCORE -DDBL_ARGS to match Fortran symbols.
 */

#ifdef UNDERSCORE
#define MSKBITS          mskbits_
#define GWXREVFLAG       gwxrevflag_
#define GWXOPEN          gwxopen_
#define GWXWINOPEN       gwxwinopen_
#define GWXCLEAR         gwxclear_
#define GWXSTATUS        gwxstatus_
#define GWXRESIZE        gwxresize_
#define GWXRESET         gwxreset_
#define GWXCLOSE         gwxclose_
#define GWXFLUSH         gwxflush_
#define GWXLINE          gwxline_
#define GWXDASH          gwxdash_
#define GWXCURS          gwxcurs_
#define GWXCURSC         gwxcursc_
#define GWXPEN           gwxpen_
#define GWXDESTROY       gwxdestroy_
#define GWXLINEZ         gwxlinez_
#define GWXPOLY          gwxpoly_
#define GWXSTRING        gwxstring_
#define GWXSETCOLOR      gwxsetcolor_
#define GWXSETBGCOLOR    gwxsetbgcolor_
#define GWXCOLORNAME2RGB gwxcolorname2rgb_
#define GWXALLOCRGBCOLOR gwxallocrgbcolor_
#define GWXFREECOLOR     gwxfreecolor_
#define GWXDISPLAYBUFFER gwxdisplaybuffer_
#define GWXDRAWTOBUFFER  gwxdrawtobuffer_
#define GWXDRAWTOWINDOW  gwxdrawtowindow_
#else
#define MSKBITS          mskbits
#define GWXREVFLAG       gwxrevflag
#define GWXOPEN          gwxopen
#define GWXWINOPEN       gwxwinopen
#define GWXCLEAR         gwxclear
#define GWXSTATUS        gwxstatus
#define GWXRESIZE        gwxresize
#define GWXRESET         gwxreset
#define GWXCLOSE         gwxclose
#define GWXFLUSH         gwxflush
#define GWXLINE          gwxline
#define GWXDASH          gwxdash
#define GWXCURS          gwxcurs
#define GWXCURSC         gwxcursc
#define GWXPEN           gwxpen
#define GWXDESTROY       gwxdestroy
#define GWXLINEZ         gwxlinez
#define GWXPOLY          gwxpoly
#define GWXSTRING        gwxstring
#define GWXSETCOLOR      gwxsetcolor
#define GWXSETBGCOLOR    gwxsetbgcolor
#define GWXCOLORNAME2RGB gwxcolorname2rgb
#define GWXALLOCRGBCOLOR gwxallocrgbcolor
#define GWXFREECOLOR     gwxfreecolor
#define GWXDISPLAYBUFFER gwxdisplaybuffer
#define GWXDRAWTOBUFFER  gwxdrawtobuffer
#define GWXDRAWTOWINDOW  gwxdrawtowindow
#endif

typedef unsigned int uint;

void MSKBITS(int *a, int *b, int *c) {
    (void)a; (void)b; (void)c;
}
void GWXREVFLAG(int *revflag) { (void)revflag; }
void GWXOPEN(int *xsizeroot, int *ysizeroot, int *depth) {
    (void)xsizeroot; (void)ysizeroot; (void)depth;
}
void GWXWINOPEN(int *xstart, int *ystart, int *xsize, int *ysize) {
    (void)xstart; (void)ystart; (void)xsize; (void)ysize;
}
void GWXCLEAR(void) {}
void GWXSTATUS(uint *xstart, uint *ystart, uint *xsize, uint *ysize) {
    if (xstart) *xstart = 0;
    if (ystart) *ystart = 0;
    if (xsize)  *xsize  = 800;
    if (ysize)  *ysize  = 600;
}
void GWXCLOSE(void) {}
void GWXDESTROY(void) {}
void GWXFLUSH(void) {}
void GWXDISPLAYBUFFER(void) {}
void GWXDRAWTOBUFFER(void) {}
void GWXDRAWTOWINDOW(void) {}
void GWXLINE(int *x1, int *y1, int *x2, int *y2) {
    (void)x1; (void)y1; (void)x2; (void)y2;
}
void GWXRESIZE(int *x, int *y) { (void)x; (void)y; }
void GWXLINEZ(int *ix, int *iy, int *n) { (void)ix; (void)iy; (void)n; }
void GWXPOLY(int *x_coord, int *y_coord, int *n_coord) {
    (void)x_coord; (void)y_coord; (void)n_coord;
}
void GWXSETCOLOR(int *pixel) { (void)pixel; }
void GWXSETBGCOLOR(int *pixel) { (void)pixel; }
void GWXCOLORNAME2RGB(int *red, int *grn, int *blu,
                      char *name, int *namelen) {
    (void)name; (void)namelen;
    if (red) *red = 0;
    if (grn) *grn = 0;
    if (blu) *blu = 0;
}
void GWXALLOCRGBCOLOR(int *red, int *grn, int *blu, int *ic) {
    (void)red; (void)grn; (void)blu;
    if (ic) *ic = 0;
}
void GWXFREECOLOR(int *pix) { (void)pix; }
void GWXSTRING(int *x, int *y, char *string, int *length) {
    (void)x; (void)y; (void)string; (void)length;
}
void GWXDASH(int *lmask) { (void)lmask; }
void GWXRESET(void) {}
void GWXPEN(int *ipen) { (void)ipen; }
void GWXCURS(int *x, int *y, int *state) {
    if (x) *x = 0;
    if (y) *y = 0;
    if (state) *state = 0;
}
void GWXCURSC(int *x, int *y, int *btn) {
    if (x) *x = 0;
    if (y) *y = 0;
    if (btn) *btn = 0;
}
STUBEOF

    # Patch config.make: remove X11 dependency, use stub
    sed -i '' 's|^LINKLIB.*|LINKLIB =|' config.make
    sed -i '' 's|^INCDIR.*|INCDIR =|' config.make
    sed -i '' 's|^WOBJ.*|WOBJ = Xwin2_stub.o|' config.make
    sed -i '' 's|^WSRC.*|WSRC = .|' config.make

    # Add build rule for stub to Makefile.all
    echo '' >> Makefile.all
    echo 'Xwin2_stub.o: Xwin2_stub.c' >> Makefile.all
    echo '	$(CC) -c $(CFLAGS) Xwin2_stub.c' >> Makefile.all
else
    # Fix X11 library path for macOS (XQuartz installs to /opt/X11)
    sed -i '' 's|LINKLIB = -L/usr/X11R6/lib -lX11|LINKLIB = -L/opt/X11/lib -lX11|' config.make
fi

make -f Makefile.all lib
echo "plotlib built: $(ls libPlt_gDP.a)"

# ── 5. Build eispack (libeispack.a) ──────────────────────────────────
echo ""
echo "Building eispack..."
cd "$AVLSRC/eispack"
make -f Makefile.gfortran DP="-fdefault-real-8"
echo "eispack built: $(ls libeispack.a)"

# ── 6. Build AVL binary ──────────────────────────────────────────────
echo ""
echo "Building AVL..."
cd "$AVLSRC/bin"

# Use the gfortranDP Makefile (self-contained LAPACK, double-precision)
cp Makefile.gfortranDP Makefile

if [[ "$USE_STUBS" == true ]]; then
    # Remove X11 link flag since we used stubs
    sed -i '' 's|^PLTLIB = -L/opt/X11/lib -lX11|PLTLIB =|' Makefile
fi

make avl
echo "AVL built successfully!"

# ── 7. Install ────────────────────────────────────────────────────────
echo ""
echo "Installing to: $OUTPUT"
mkdir -p "$(dirname "$OUTPUT")"
cp "$AVLSRC/bin/avl" "$OUTPUT"
chmod +x "$OUTPUT"

# ── 8. Verify ─────────────────────────────────────────────────────────
echo ""
echo "Verifying binary..."
file "$OUTPUT"

# Quick headless test
GEOMETRY="$PROJECT_DIR/friend files/uav22.avl"
if [[ -f "$GEOMETRY" ]]; then
    echo ""
    echo "Running headless test with uav22.avl..."
    TESTOUT=$(echo -e "PLOP\nG F\n\nquit\n" | "$OUTPUT" "$GEOMETRY" 2>&1 | head -5)
    echo "$TESTOUT"
fi

echo ""
echo "=== Build complete! ==="
echo "Binary: $OUTPUT"
echo ""
echo "NOTE: This binary is for macOS DEVELOPMENT TESTING ONLY."
echo "Production code MUST use avl352.exe (Windows). See CLAUDE.md."
