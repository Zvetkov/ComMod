from os.path import join, dirname, abspath

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

_STYLESHEET = join(dirname(abspath(__file__)), 'resources/style.qss')
""" str: Main stylesheet. """


def _apply_base_theme(app: QApplication):
    """ Apply base theme to the application.

        Args:
            app (QApplication): QApplication instance.
    """
    app.setStyle('Fusion')
    with open(_STYLESHEET) as stylesheet:
        app.setStyleSheet(stylesheet.read())


def dark(app: QApplication):
    """ Apply Dark Theme to the Qt application instance.

        Args:
            app (QApplication): QApplication instance.
    """

    darkPalette = QPalette()

    # base
    darkPalette.setColor(QPalette.WindowText, "#b4b4b4")
    darkPalette.setColor(QPalette.Button, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.Light, QColor(180, 180, 180))
    darkPalette.setColor(QPalette.Midlight, QColor(90, 90, 90))
    darkPalette.setColor(QPalette.Dark, QColor(35, 35, 35))
    darkPalette.setColor(QPalette.Text, QColor(190, 190, 190))
    darkPalette.setColor(QPalette.PlaceholderText, QColor(180, 84, 10))
    darkPalette.setColor(QPalette.BrightText, QColor(180, 180, 180))
    darkPalette.setColor(QPalette.ButtonText, QColor(180, 180, 180))
    darkPalette.setColor(QPalette.Base, QColor(42, 42, 42))
    darkPalette.setColor(QPalette.Window, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.Shadow, QColor(20, 20, 20))
    darkPalette.setColor(QPalette.Highlight, QColor(255, 165, 0))
    darkPalette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    darkPalette.setColor(QPalette.Link, QColor(56, 252, 196))
    darkPalette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
    darkPalette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
    darkPalette.setColor(QPalette.ToolTipText, QColor(180, 180, 180))

    # disabled
    darkPalette.setColor(QPalette.Disabled, QPalette.WindowText,
                         QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Disabled, QPalette.Text,
                         QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Disabled, QPalette.ButtonText,
                         QColor(127, 127, 127))
    darkPalette.setColor(QPalette.Disabled, QPalette.Highlight,
                         QColor(80, 80, 80))
    darkPalette.setColor(QPalette.Disabled, QPalette.HighlightedText,
                         QColor(127, 127, 127))

    app.setPalette(darkPalette)

    # _apply_base_theme(app)
    # extra = {
    #     # Density Scale
    #     'density_scale': '-1',
    # }
    # apply_stylesheet(app, theme='dark_amber.xml', extra=extra)
    # map(lambda x: x.redraw(), app.topLevelWidgets())
    # map(lambda x: x.update(), app.topLevelWindows())
