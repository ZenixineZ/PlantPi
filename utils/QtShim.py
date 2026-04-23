#!/usr/bin/env python3
"""Qt5/6 compatibility shim.

Import Qt classes and unified enum aliases from here instead of
using per-file try/except blocks or _QT == 6 ternary expressions.
"""

try:
    from PyQt5.QtWidgets import (
        QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
        QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
        QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMainWindow, QMessageBox, QProxyStyle, QPushButton,
        QSizePolicy, QSpinBox, QSplitter, QSplitterHandle, QStackedWidget,
        QStyle, QTabBar, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    )
    from PyQt5.QtCore import Qt, QObject, QSize, QRectF, pyqtSignal, QTimer
    from PyQt5.QtGui import (
        QColor, QBrush, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QFontMetrics
    )
    _QT = 5
except ImportError:
    from PyQt6.QtWidgets import (
        QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
        QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
        QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMainWindow, QMessageBox, QProxyStyle, QPushButton,
        QSizePolicy, QSpinBox, QSplitter, QSplitterHandle, QStackedWidget,
        QStyle, QTabBar, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    )
    from PyQt6.QtCore import Qt, QObject, QSize, QRectF, pyqtSignal, QTimer
    from PyQt6.QtGui import (
        QColor, QBrush, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QFontMetrics
    )
    _QT = 6


def exec_app(app):
    """Run the Qt event loop — works with both PyQt5 (exec_) and PyQt6 (exec)."""
    return app.exec_() if _QT == 5 else app.exec()


def exec_dialog(dlg):
    """Run a QDialog/QFileDialog event loop across PyQt5/6."""
    return dlg.exec_() if _QT == 5 else dlg.exec()


class FileDialog:
    AcceptSave         = QFileDialog.AcceptMode.AcceptSave        if _QT == 6 else QFileDialog.AcceptSave
    DontUseNativeDialog = QFileDialog.Option.DontUseNativeDialog  if _QT == 6 else QFileDialog.DontUseNativeDialog
    AnyFile            = QFileDialog.FileMode.AnyFile             if _QT == 6 else QFileDialog.AnyFile


def font_text_width(font, text):
    """Return the pixel width of text for a QFontMetrics via boundingRect."""
    return QFontMetrics(font).boundingRect(text).width()


# ---------------------------------------------------------------------------
# Unified enum aliases — one ternary per value, right here, never elsewhere
# ---------------------------------------------------------------------------

class Align:
    HCenter = Qt.AlignmentFlag.AlignHCenter if _QT == 6 else Qt.AlignHCenter
    Center  = Qt.AlignmentFlag.AlignCenter  if _QT == 6 else Qt.AlignCenter
    Right   = Qt.AlignmentFlag.AlignRight   if _QT == 6 else Qt.AlignRight
    Left    = Qt.AlignmentFlag.AlignLeft    if _QT == 6 else Qt.AlignLeft
    Top     = Qt.AlignmentFlag.AlignTop     if _QT == 6 else Qt.AlignTop


class Frame:
    VLine       = QFrame.Shape.VLine       if _QT == 6 else QFrame.VLine
    HLine       = QFrame.Shape.HLine       if _QT == 6 else QFrame.HLine
    StyledPanel = QFrame.Shape.StyledPanel if _QT == 6 else QFrame.StyledPanel
    Sunken      = QFrame.Shadow.Sunken     if _QT == 6 else QFrame.Sunken


class SizePolicy:
    Expanding = QSizePolicy.Policy.Expanding if _QT == 6 else QSizePolicy.Expanding


class MessageBox:
    Yes = QMessageBox.StandardButton.Yes if _QT == 6 else QMessageBox.Yes
    No  = QMessageBox.StandardButton.No  if _QT == 6 else QMessageBox.No


class ItemView:
    ExtendedSelection = (QAbstractItemView.SelectionMode.ExtendedSelection if _QT == 6
                         else QAbstractItemView.ExtendedSelection)


class Painter:
    Antialiasing = QPainter.RenderHint.Antialiasing if _QT == 6 else QPainter.Antialiasing


class Font:
    Bold = QFont.Weight.Bold if _QT == 6 else QFont.Bold


class Style:
    SH_ToolTip_WakeUpDelay = (QStyle.StyleHint.SH_ToolTip_WakeUpDelay if _QT == 6
                               else QStyle.SH_ToolTip_WakeUpDelay)


class Pen:
    Dash     = Qt.PenStyle.DashLine    if _QT == 6 else Qt.DashLine
    Dot      = Qt.PenStyle.DotLine     if _QT == 6 else Qt.DotLine
    NoPen    = Qt.PenStyle.NoPen       if _QT == 6 else Qt.NoPen
    RoundCap = Qt.PenCapStyle.RoundCap if _QT == 6 else Qt.RoundCap


class Brush:
    NoBrush = Qt.BrushStyle.NoBrush if _QT == 6 else Qt.NoBrush


class ScrollBar:
    AlwaysOff = Qt.ScrollBarPolicy.ScrollBarAlwaysOff if _QT == 6 else Qt.ScrollBarAlwaysOff


class Mouse:
    Left = Qt.MouseButton.LeftButton if _QT == 6 else Qt.LeftButton


class Focus:
    Strong = Qt.FocusPolicy.StrongFocus if _QT == 6 else Qt.StrongFocus


class Orientation:
    Horizontal = Qt.Orientation.Horizontal if _QT == 6 else Qt.Horizontal


class Key:
    X = Qt.Key.Key_X if _QT == 6 else Qt.Key_X
