/*
 * SPDX-FileCopyrightText: 2017-2017 CSSlayer <wengxt@gmail.com>
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 *
 */
#ifndef _FCITX_UI_CLASSIC_XCBINPUTWINDOW_H_
#define _FCITX_UI_CLASSIC_XCBINPUTWINDOW_H_

#include <array>
#include "inputwindow.h"
#include "xcbwindow.h"

namespace fcitx {
namespace classicui {

class XCBInputWindow : public XCBWindow, protected InputWindow {
public:
    XCBInputWindow(XCBUI *ui);

    ~XCBInputWindow() override;
    void postCreateWindow() override;
    void update(InputContext *inputContext);
    void updatePosition(InputContext *inputContext);

    bool filterEvent(xcb_generic_event_t *event) override;

    void updateDPI(InputContext *inputContext);

private:
    void repaint();
    cairo_surface_t *prepareFrame(int width, int height);
    void releaseFrames();
    std::pair<unsigned int, unsigned int>
    canvasSize(unsigned int panelWidth, unsigned int panelHeight) const;
    void updateBlur(unsigned int width, unsigned int height);
    void setInputShape(unsigned int width, unsigned int height);
    void setFrameBackground();
    void presentFrame();
    void copyFrame(int index);
    struct Frame {
        xcb_pixmap_t pixmap = XCB_NONE;
        UniqueCPtr<cairo_surface_t, cairo_surface_destroy> surface;
        int width = 0;
        int height = 0;
    };
    std::array<Frame, 2> frames_;
    xcb_window_t frameWindow_ = XCB_NONE;
    xcb_gcontext_t copyGC_ = XCB_NONE;
    int frontFrame_ = -1;
    int preparedFrame_ = 0;
    unsigned int panelWidth_ = 0;
    unsigned int panelHeight_ = 0;
    unsigned int presentedWidth_ = 0;
    unsigned int presentedHeight_ = 0;
    bool shapeAvailable_ = false;
    xcb_atom_t atomBlur_;
    int dpi_ = -1;
};
} // namespace classicui
} // namespace fcitx

#endif // _FCITX_UI_CLASSIC_XCBINPUTWINDOW_H_
