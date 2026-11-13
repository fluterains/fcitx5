/*
 * SPDX-FileCopyrightText: 2017-2017 CSSlayer <wengxt@gmail.com>
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 *
 */

#include "xcbinputwindow.h"
#include <algorithm>
#include <cmath>
#include <pango/pangocairo.h>
#include <cairo-xcb.h>
#include <xcb/xcb_aux.h>
#include <xcb/xcb_icccm.h>
#include <xcb/shape.h>
#include "fcitx-utils/rect.h"

namespace fcitx::classicui {

XCBInputWindow::XCBInputWindow(XCBUI *ui)
    : XCBWindow(ui), InputWindow(ui->parent()),
      atomBlur_(ui_->parent()->xcb()->call<IXCBModule::atom>(
          ui_->displayName(), "_KDE_NET_WM_BLUR_BEHIND_REGION", false)) {}

XCBInputWindow::~XCBInputWindow() { releaseFrames(); }

void XCBInputWindow::postCreateWindow() {
    auto *shape =
        xcb_get_extension_data(ui_->connection(), &xcb_shape_id);
    shapeAvailable_ = false;
    if (shape && shape->present) {
        auto version = makeUniqueCPtr(xcb_shape_query_version_reply(
            ui_->connection(), xcb_shape_query_version(ui_->connection()), nullptr));
        shapeAvailable_ = version && (version->major_version > 1 ||
            (version->major_version == 1 && version->minor_version >= 1));
    }
    auto *screen = xcb_aux_get_screen(ui_->connection(), ui_->defaultScreen());
    stableCanvas_ = shapeAvailable_ &&
        xcb_aux_get_depth_of_visual(screen, vid_) == 32;

    if (ui_->ewmh()->_NET_WM_WINDOW_TYPE_POPUP_MENU &&
        ui_->ewmh()->_NET_WM_WINDOW_TYPE) {
        xcb_ewmh_set_wm_window_type(
            ui_->ewmh(), wid_, 1, &ui_->ewmh()->_NET_WM_WINDOW_TYPE_POPUP_MENU);
    }

    if (ui_->ewmh()->_NET_WM_PID) {
        xcb_ewmh_set_wm_pid(ui_->ewmh(), wid_, getpid());
    }

    const char name[] = "Fcitx5 Input Window";
    xcb_icccm_set_wm_name(ui_->connection(), wid_, XCB_ATOM_STRING, 8,
                          sizeof(name) - 1, name);
    const char klass[] = "fcitx\0fcitx";
    xcb_icccm_set_wm_class(ui_->connection(), wid_, sizeof(klass) - 1, klass);
    addEventMaskToWindow(
        ui_->connection(), wid_,
        XCB_EVENT_MASK_BUTTON_PRESS | XCB_EVENT_MASK_BUTTON_RELEASE |
            XCB_EVENT_MASK_POINTER_MOTION | XCB_EVENT_MASK_EXPOSURE |
            XCB_EVENT_MASK_LEAVE_WINDOW);
}

void XCBInputWindow::updatePosition(InputContext *inputContext) {
    if (!visible()) {
        resetPositionAdjustment();
        return;
    }
    int x, y;

    // add support of input panel offset here.
    // TODO: RTL support.
    auto &theme = parent_->theme();
    int leftSW, rightSW, actualWidth;
    leftSW = theme.inputPanel->shadowMargin->marginLeft.value();
    rightSW = theme.inputPanel->shadowMargin->marginRight.value();

    compositionCursorRect(inputContext);
    followHostWindow(inputContext);
    const auto anchor = compositionCursorRect(inputContext);
    if (!positionAdjustmentActive_ || positionContext_.get() != inputContext ||
        positionAnchor_ != anchor) {
        horizontalOverflowShift_ = 0;
        positionContext_ = inputContext->watch();
        positionAnchor_ = anchor;
        positionAdjustmentActive_ = true;
    }
    x = anchor.left();

    const double scale = (dpi_ > 0 ? dpi_ : 96) / 96.0;
    const int gap = std::max(1, static_cast<int>(std::lround(8 * scale)));
    const int fallbackHeight =
        std::max(1, static_cast<int>(std::lround(10 * scale)));
    const auto cursor = inputContext->cursorRect();
    // Keep the horizontal composition anchor, but clear the whole preview's
    // vertical extent when it wraps or the client supplies its height late.
    const int previewTop = std::min(anchor.top(), cursor.top());
    const int previewBottom = std::max(
        anchor.top() + (anchor.height() > 0 ? anchor.height() : fallbackHeight),
        cursor.top() + (cursor.height() > 0 ? cursor.height() : fallbackHeight));
    // Work with the full painted panel, including its shadows. The retained
    // transparent canvas can be taller and must not influence placement.
    const int panelHeight = static_cast<int>(panelHeight_);
    y = previewBottom + gap;

    actualWidth = panelWidth_ - leftSW - rightSW;
    actualWidth = actualWidth <= 0 ? panelWidth_ : actualWidth;

    const Rect *closestScreen = nullptr;
    int shortestDistance = INT_MAX;
    for (const auto &rect : ui_->screenRects()) {
        int thisDistance = rect.first.distance(anchor.left(), anchor.top());
        if (thisDistance < shortestDistance) {
            shortestDistance = thisDistance;
            closestScreen = &rect.first;
        }
    }

    if (closestScreen) {
        int newX, newY;

        if (x < closestScreen->left()) {
            newX = closestScreen->left();
        } else {
            newX = x;
        }

        const int below = previewBottom + gap;
        const int above = previewTop - gap - panelHeight;
        const int screenTop = closestScreen->top();
        const int screenBottom = closestScreen->bottom();
        if (below >= screenTop && below + panelHeight <= screenBottom) {
            newY = below;
        } else if (above >= screenTop && above + panelHeight <= screenBottom) {
            newY = above;
        } else {
            // If neither side can hold the panel, use the roomier side and
            // keep as much of it on this monitor as possible.
            const int roomBelow = screenBottom - below;
            const int roomAbove = previewTop - gap - screenTop;
            newY = std::clamp(roomBelow >= roomAbove ? below : above,
                              screenTop,
                              std::max(screenTop, screenBottom - panelHeight));
        }

        const int overflow = std::max(
            0, newX + actualWidth - closestScreen->right());
        horizontalOverflowShift_ =
            std::max(horizontalOverflowShift_, overflow);
        newX = std::max(closestScreen->left(),
                        newX - horizontalOverflowShift_);

        x = newX;
        y = newY;
    }

    // exclude shadow border width
    x -= leftSW;

    xcb_params_configure_window_t wc;
    wc.x = x;
    wc.y = y;
    wc.stack_mode = XCB_STACK_MODE_ABOVE;
    xcb_aux_configure_window(ui_->connection(), wid_,
                             XCB_CONFIG_WINDOW_STACK_MODE |
                                 XCB_CONFIG_WINDOW_X | XCB_CONFIG_WINDOW_Y,
                             &wc);
}

void XCBInputWindow::updateDPI(InputContext *inputContext) {
    const auto anchor = compositionCursorRect(inputContext);
    dpi_ = ui_->dpiByPosition(anchor.left(), anchor.top());

    setFontDPI(dpi_);
}

void XCBInputWindow::update(InputContext *inputContext) {
    if (!wid_) {
        return;
    }
    auto oldVisible = visible();
    if (inputContext) {
        updateDPI(inputContext);
    }
    auto [width, height] = InputWindow::update(inputContext);
    if (!visible()) {
        if (oldVisible) {
            xcb_unmap_window(ui_->connection(), wid_);
        }
        resetPositionAdjustment();
        return;
    }

    panelWidth_ = width;
    panelHeight_ = height;
    const auto [canvasWidth, canvasHeight] = canvasSize(width, height);

    auto *frame = prepareFrame(canvasWidth, canvasHeight);
    if (!frame) {
        return;
    }
    auto *c = cairo_create(frame);
    paint(c, panelWidth_, panelHeight_, /*scale=*/1.0);
    cairo_destroy(c);
    cairo_surface_flush(frame);
    setFrameBackground();

    // The monitor-wide canvas stays fixed while the painted panel keeps its
    // exact layout size. Typing therefore never resizes the top-level window.
    if (canvasWidth != static_cast<unsigned int>(this->width()) ||
        canvasHeight != static_cast<unsigned int>(this->height()) ||
        frameWindow_ != wid_) {
        resize(canvasWidth, canvasHeight);
    }

    updateBlur(panelWidth_, panelHeight_);
    updatePosition(inputContext);
    presentFrame();
    setInputShape(panelWidth_, panelHeight_);
    if (!oldVisible) {
        xcb_map_window(ui_->connection(), wid_);
    }
    cairo_surface_flush(surface_.get());
    xcb_flush(ui_->connection());
}

void XCBInputWindow::followHostWindow(InputContext *ic) {
    if (!anchorActive_ || hostContext_.get() != ic) {
        anchorWindow_ = XCB_NONE;
        hostContext_.unwatch();
    }
    if (!anchorActive_) {
        return;
    }
    const bool first = anchorWindow_ == XCB_NONE;
    if (first) {
        auto focus = makeUniqueCPtr(xcb_get_input_focus_reply(
            ui_->connection(), xcb_get_input_focus(ui_->connection()), nullptr));
        if (!focus || focus->focus <= XCB_INPUT_FOCUS_POINTER_ROOT) {
            return;
        }
        anchorWindow_ = focus->focus;
        hostContext_ = ic->watch();
    }
    auto origin = makeUniqueCPtr(xcb_translate_coordinates_reply(
        ui_->connection(), xcb_translate_coordinates(ui_->connection(),
            anchorWindow_, ui_->root(), 0, 0), nullptr));
    if (!origin) {
        anchorWindow_ = XCB_NONE;
        return;
    }
    if (!first) {
        compositionAnchor_ = compositionAnchor_.translated(
            origin->dst_x - hostX_, origin->dst_y - hostY_);
    }
    hostX_ = origin->dst_x;
    hostY_ = origin->dst_y;
}

void XCBInputWindow::resetPositionAdjustment() {
    anchorWindow_ = XCB_NONE;
    hostContext_.unwatch();
    horizontalOverflowShift_ = 0;
    positionContext_.unwatch();
    positionAdjustmentActive_ = false;
}

bool XCBInputWindow::filterEvent(xcb_generic_event_t *event) {
    uint8_t response_type = event->response_type & ~0x80;
    switch (response_type) {

    case XCB_EXPOSE: {
        auto *expose = reinterpret_cast<xcb_expose_event_t *>(event);
        if (expose->window == wid_) {
            if (expose->count == 0 && frontFrame_ >= 0) {
                // Expose does not change content: restore the completed frame.
                copyFrame(frontFrame_);
                xcb_flush(ui_->connection());
            }
            return true;
        }
        break;
    }
    case XCB_BUTTON_PRESS: {
        auto *buttonPress = reinterpret_cast<xcb_button_press_event_t *>(event);
        if (buttonPress->event != wid_) {
            break;
        }
        if (buttonPress->detail == XCB_BUTTON_INDEX_1) {
            click(buttonPress->event_x, buttonPress->event_y);
        } else if (buttonPress->detail == XCB_BUTTON_INDEX_4) {
            wheel(/*up=*/true);
        } else if (buttonPress->detail == XCB_BUTTON_INDEX_5) {
            wheel(/*up=*/false);
        }
        return true;
    }
    case XCB_MOTION_NOTIFY: {
        auto *motion = reinterpret_cast<xcb_motion_notify_event_t *>(event);
        if (motion->event == wid_) {
            if (hover(motion->event_x, motion->event_y)) {
                repaint();
            }
            return true;
        }
        break;
    }
    case XCB_LEAVE_NOTIFY: {
        auto *leave = reinterpret_cast<xcb_leave_notify_event_t *>(event);
        if (leave->event == wid_) {
            if (hover(-1, -1)) {
                repaint();
            }
            return true;
        }
        break;
    }
    }
    return false;
}

void XCBInputWindow::releaseFrames() {
    contentSurface_.reset();
    for (auto &frame : frames_) {
        frame.surface.reset();
        if (frame.pixmap != XCB_NONE) {
            xcb_free_pixmap(ui_->connection(), frame.pixmap);
        }
        frame.pixmap = XCB_NONE;
        frame.width = frame.height = 0;
    }
    if (copyGC_ != XCB_NONE) {
        xcb_free_gc(ui_->connection(), copyGC_);
        copyGC_ = XCB_NONE;
    }
    frontFrame_ = -1;
    presentedWidth_ = presentedHeight_ = 0;
    frameWindow_ = XCB_NONE;
}

std::pair<unsigned int, unsigned int>
XCBInputWindow::canvasSize(unsigned int panelWidth,
                           unsigned int panelHeight) const {
    // Root-visual windows cannot display an alpha-cleared margin. Old Shape
    // servers also cannot make the margin click-through.
    if (!stableCanvas_) {
        return {panelWidth, panelHeight};
    }
    unsigned int canvasWidth = panelWidth;
    for (const auto &screen : ui_->screenRects()) {
        canvasWidth = std::max(
            canvasWidth, static_cast<unsigned int>(screen.first.width()));
    }
    const unsigned int canvasHeight =
        std::max(static_cast<unsigned int>(height()), panelHeight);
    return {canvasWidth, canvasHeight};
}

void XCBInputWindow::updateBlur(unsigned int width, unsigned int height) {
    if (!atomBlur_) {
        return;
    }
    Rect rect(0, 0, width, height);
    shrink(rect, *ui_->parent()->theme().inputPanel->blurMargin);
    if (!*ui_->parent()->theme().inputPanel->enableBlur || rect.isEmpty()) {
        xcb_delete_property(ui_->connection(), wid_, atomBlur_);
        return;
    }

    std::vector<uint32_t> data;
    if (ui_->parent()->theme().inputPanel->blurMask->empty()) {
        data.push_back(rect.left());
        data.push_back(rect.top());
        data.push_back(rect.width());
        data.push_back(rect.height());
    } else {
        auto region = parent_->theme().mask(
            parent_->theme().maskConfig(), width, height);
        for (const auto &maskRect : region) {
            data.push_back(maskRect.left());
            data.push_back(maskRect.top());
            data.push_back(maskRect.width());
            data.push_back(maskRect.height());
        }
    }
    xcb_change_property(ui_->connection(), XCB_PROP_MODE_REPLACE, wid_,
                        atomBlur_, XCB_ATOM_CARDINAL, 32, data.size(),
                        data.data());
}

void XCBInputWindow::setInputShape(unsigned int width, unsigned int height) {
    if (!shapeAvailable_) {
        return;
    }
    xcb_rectangle_t rectangle;
    rectangle.x = 0;
    rectangle.y = 0;
    rectangle.width = width;
    rectangle.height = height;
    xcb_shape_rectangles(ui_->connection(), XCB_SHAPE_SO_SET,
                         XCB_SHAPE_SK_INPUT, XCB_CLIP_ORDERING_UNSORTED, wid_,
                         0, 0, 1, &rectangle);
}

cairo_surface_t *XCBInputWindow::prepareFrame(int width, int height) {
    auto *conn = ui_->connection();
    if (frameWindow_ != wid_) {
        releaseFrames();
        frameWindow_ = wid_;
        copyGC_ = xcb_generate_id(conn);
        const uint32_t graphicsExposures = 0;
        xcb_create_gc(conn, copyGC_, wid_, XCB_GC_GRAPHICS_EXPOSURES,
                      &graphicsExposures);
    }
    preparedFrame_ = frontFrame_ == 0 ? 1 : 0;
    auto &frame = frames_[preparedFrame_];
    if (!frame.surface || frame.width < width || frame.height < height) {
        frame.surface.reset();
        if (frame.pixmap != XCB_NONE) {
            xcb_free_pixmap(conn, frame.pixmap);
        }
        // The frame canvas is intentionally larger than the visible panel so
        // content can grow without resizing and exposing the top-level window.
        frame.width = std::max(frame.width, width);
        frame.height = std::max(frame.height, height);
        auto *screen = xcb_aux_get_screen(conn, ui_->defaultScreen());
        auto visual = vid_ ? vid_ : screen->root_visual;
        frame.pixmap = xcb_generate_id(conn);
        xcb_create_pixmap(conn, xcb_aux_get_depth_of_visual(screen, visual),
                          frame.pixmap, wid_, frame.width, frame.height);
        frame.surface.reset(cairo_xcb_surface_create(
            conn, frame.pixmap, xcb_aux_find_visual_by_id(screen, visual),
            frame.width, frame.height));
    }
    if (cairo_surface_status(frame.surface.get()) != CAIRO_STATUS_SUCCESS) {
        return nullptr;
    }
    contentSurface_.reset(cairo_surface_reference(frame.surface.get()));
    auto *cr = cairo_create(frame.surface.get());
    cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR);
    cairo_paint(cr);
    cairo_destroy(cr);
    return frame.surface.get();
}

void XCBInputWindow::setFrameBackground() {
    const uint32_t pixmap = frames_[preparedFrame_].pixmap;
    xcb_change_window_attributes(ui_->connection(), wid_, XCB_CW_BACK_PIXMAP,
                                  &pixmap);
}

void XCBInputWindow::copyFrame(int index) {
    const unsigned int copyWidth = std::max(presentedWidth_, panelWidth_);
    const unsigned int copyHeight = std::max(presentedHeight_, panelHeight_);
    xcb_copy_area(ui_->connection(), frames_[index].pixmap, wid_, copyGC_, 0,
                   0, 0, 0, copyWidth, copyHeight);
    cairo_surface_mark_dirty(surface_.get());
}

void XCBInputWindow::presentFrame() {
    frontFrame_ = preparedFrame_;
    // One server-side copy replaces the complete window image.
    copyFrame(frontFrame_);
    presentedWidth_ = panelWidth_;
    presentedHeight_ = panelHeight_;
}

void XCBInputWindow::repaint() {
    if (!visible()) {
        return;
    }
    if (auto *surface = prepareFrame(width(), height())) {
        cairo_t *c = cairo_create(surface);
        paint(c, panelWidth_, panelHeight_, /*scale=*/1.0);
        cairo_destroy(c);
        cairo_surface_flush(surface);
        setFrameBackground();
        presentFrame();
        setInputShape(panelWidth_, panelHeight_);
        xcb_flush(ui_->connection());
    }
}

} // namespace fcitx::classicui
