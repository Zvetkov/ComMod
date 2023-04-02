from ctypes.wintypes import MSG
from win32con import WM_NCHITTEST, \
    HTTOPLEFT, HTBOTTOMRIGHT, HTTOPRIGHT, HTBOTTOMLEFT, \
    HTTOP, HTBOTTOM, HTLEFT, HTRIGHT

from PySide6.QtCore import Qt, QMetaObject, Signal, Slot, QPoint
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
                               QLabel, QSizePolicy, QGraphicsDropShadowEffect,
                               QLineEdit, QApplication)

""" str: Frameless window stylesheet. """


class WindowDragger(QWidget):
    """ Window dragger.

        Args:
            window (QWidget): Associated window.
            parent (QWidget, optional): Parent widget.
    """
    doubleClicked = Signal()

    def __init__(self, window, parent=None):
        QWidget.__init__(self, parent)

        self._window = window
        self._mousePressed = False
        self._windowPos = self._window.pos()
        self._mousePos = QCursor.pos()

    def mousePressEvent(self, event):
        self._mousePressed = True
        self._mousePos = event.globalPos()
        self._windowPos = self._window.pos()

    def mouseMoveEvent(self, event):
        if self._window.isMaximized():
            if self._window.btnMaximize.isVisible():
                self._window.on_btnMaximize_clicked()
            else:
                self._window.on_btnRestore_clicked()

        if self._windowPos == QPoint(0, 0):
            # recenter window if it's being dragged from maximised state
            self._windowPos = self._mousePos - QPoint(self._window.width() / 2, 0)
        self._window.move(self._windowPos + (event.globalPos()
                                             - self._mousePos))

    def mouseReleaseEvent(self, event):
        self._mousePressed = False

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()


class ModernWindow(QWidget):
    """ Modern window.

        Args:
            w (QWidget): Main widget.
            parent (QWidget, optional): Parent widget.
    """
    BORDER_WIDTH = 5

    def __init__(self, w, disable_maximization: bool = False):
        QWidget.__init__(self)

        self._w = w
        self._w.ModernWindow = self
        self.maximization_disabled = disable_maximization

        # set window flags
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.BypassWindowManagerHint)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setup_ui()

        contentLayout = QHBoxLayout()
        contentLayout.setContentsMargins(0, 0, 0, 0)
        contentLayout.addWidget(w)

        self.windowContent.setLayout(contentLayout)

        self.setWindowTitle(w.windowTitle())
        self.setGeometry(w.geometry())

        # Adding attribute to clean up the parent window when the child is closed
        self._w.setAttribute(Qt.WA_DeleteOnClose, True)
        self._w.destroyed.connect(self.__child_was_closed)

    def setup_ui(self):
        # create title bar, content
        self.vboxWindow = QVBoxLayout(self)
        self.vboxWindow.setContentsMargins(0, 0, 0, 0)

        self.windowFrame = QWidget(self)
        self.windowFrame.setObjectName('windowFrame')

        self.vboxFrame = QVBoxLayout(self.windowFrame)
        self.vboxFrame.setContentsMargins(0, 0, 0, 0)

        self.titleBar = WindowDragger(self, self.windowFrame)
        self.titleBar.setObjectName('titleBar')
        self.titleBar.setSizePolicy(QSizePolicy(QSizePolicy.Preferred,
                                                QSizePolicy.Fixed))

        self.hboxTitle = QHBoxLayout(self.titleBar)
        self.hboxTitle.setContentsMargins(0, 0, 0, 0)
        self.hboxTitle.setSpacing(0)

        self.lblTitle = QLabel('Title')
        self.lblTitle.setObjectName('lblTitle')
        self.lblTitle.setAlignment(Qt.AlignCenter)
        self.hboxTitle.addWidget(self.lblTitle)

        spButtons = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.btnMinimize = QToolButton(self.titleBar)
        self.btnMinimize.setObjectName('btnMinimize')
        self.btnMinimize.setSizePolicy(spButtons)
        self.hboxTitle.addWidget(self.btnMinimize)

        self.btnRestore = QToolButton(self.titleBar)
        self.btnRestore.setObjectName('btnRestore')
        self.btnRestore.setSizePolicy(spButtons)
        self.btnRestore.setVisible(False)
        self.hboxTitle.addWidget(self.btnRestore)
        if self.maximization_disabled:
            self.btnRestore.hide()

        self.btnMaximize = QToolButton(self.titleBar)
        self.btnMaximize.setObjectName('btnMaximize')
        self.btnMaximize.setSizePolicy(spButtons)
        self.hboxTitle.addWidget(self.btnMaximize)
        if self.maximization_disabled:
            self.btnMaximize.hide()

        self.btnClose = QToolButton(self.titleBar)
        self.btnClose.setObjectName('btnClose')
        self.btnClose.setSizePolicy(spButtons)
        self.hboxTitle.addWidget(self.btnClose)

        self.vboxFrame.addWidget(self.titleBar)

        self.windowContent = QWidget(self.windowFrame)
        self.vboxFrame.addWidget(self.windowContent)

        self.vboxWindow.addWidget(self.windowFrame)

        self.layout().setContentsMargins(5, 5, 5, 5)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setOffset(0)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.windowFrame.setGraphicsEffect(shadow)

        # automatically connect slots
        QMetaObject.connectSlotsByName(self)

    def nativeEvent(self, event, message):
        return_value, result = super().nativeEvent(event, message)
        # if you use Windows OS
        if event == b'windows_generic_MSG':
            msg = MSG.from_address(message.__int__())
            point = self.mapFromGlobal(QCursor.pos())
            x = point.x()
            y = point.y()

            # Determine whether there are other controls(i.e. widgets etc.) at the mouse position.
            if self.childAt(x, y) is not None and self.childAt(x, y) is not self.findChild(QWidget, "lblTitle"):
                if self.width() - self.BORDER_WIDTH > x > self.BORDER_WIDTH and y < self.height() - self.BORDER_WIDTH:
                    # print(f"found other element: {self.childAt(x, y)}")
                    return return_value, result

            if msg.message == WM_NCHITTEST:
                w, h = self.width(), self.height()
                lx = x < self.BORDER_WIDTH and not self.isMaximized()
                rx = x > w - self.BORDER_WIDTH and not self.isMaximized()
                ty = y < self.BORDER_WIDTH and not self.isMaximized()
                by = y > h - self.BORDER_WIDTH and not self.isMaximized()
                if lx and ty:
                    # In the upper-left corner of a window border (to resize the window diagonally).
                    return True, HTTOPLEFT
                if rx and by:
                    # In the lower-right corner of a border of a resizable window (to resize the window diagonally).
                    return True, HTBOTTOMRIGHT
                if rx and ty:
                    # In the upper-right corner of a window border  (to resize the window diagonally).
                    return True, HTTOPRIGHT
                if lx and by:
                    # In the lower-left corner of a border of a resizable window (to resize the window diagonally).
                    return True, HTBOTTOMLEFT
                if ty:
                    # In the upper-horizontal border of a window (to resize the window vertically).
                    return True, HTTOP
                if by:
                    # In the lower-horizontal border of a resizable window (to resize the window vertically).
                    return True, HTBOTTOM
                if lx:
                    # In the left border of a resizable window (to resize the window horizontally).
                    return True, HTLEFT
                if rx:
                    # In the right border of a resizable window (to resize the window horizontally).
                    return True, HTRIGHT
                # In a title bar.
                # return True, HTCAPTION

        return QWidget.nativeEvent(self, event, message)

    def __child_was_closed(self):
        self._w = None  # The child was deleted, remove the reference to it and close the parent window
        self.close()

    def closeEvent(self, event):
        if not self._w:
            event.accept()
        else:
            self._w.close()
            event.setAccepted(self._w.isHidden())

    def setWindowTitle(self, title):
        """ Set window title.

            Args:
                title (str): Title.
        """

        super(ModernWindow, self).setWindowTitle(title)
        self.lblTitle.setText("                      " + title)
        # self.lblTitle.setText(title)

    @Slot()
    def on_btnMinimize_clicked(self):
        self.setWindowState(Qt.WindowMinimized)

    @Slot()
    def on_btnRestore_clicked(self):
        self.btnRestore.setVisible(False)
        self.btnMaximize.setVisible(True)

        self.layout().setContentsMargins(5, 5, 5, 5)
        self.setWindowState(Qt.WindowNoState)

    @Slot()
    def on_btnMaximize_clicked(self):
        self.btnRestore.setVisible(True)
        self.btnMaximize.setVisible(False)

        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setWindowState(Qt.WindowMaximized)

    @Slot()
    def on_btnClose_clicked(self):
        self.close()

    @Slot()
    def mousePressEvent(self, event):
        if self.underMouse():
            focused_widget = QApplication.focusWidget()
            if isinstance(focused_widget, QLineEdit):
                focused_widget.clearFocus()
        self._w.mousePressEvent(event)

    @Slot()
    def on_titleBar_doubleClicked(self):
        if not self.maximization_disabled:
            if self.btnMaximize.isVisible():
                self.on_btnMaximize_clicked()
            else:
                self.on_btnRestore_clicked()
