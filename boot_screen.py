"""Small, skippable retro startup animation drawn entirely with Qt."""
import math
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QIcon, QLinearGradient
from PySide6.QtWidgets import QDialog
from PySide6.QtSvg import QSvgRenderer
from brand import asset

class BootScreen(QDialog):
    DURATION_MS = 3200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Ascends PS Capture program')
        self.setWindowIcon(QIcon(asset('ascend.ico')))
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setFixedSize(760,460)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.logo=QSvgRenderer(asset('ascend-mark.svg'))
        self.clock=QElapsedTimer()
        self.timer=QTimer(self); self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(17); self.timer.timeout.connect(self.tick)

    def showEvent(self,event):
        super().showEvent(event)
        screen=self.screen().availableGeometry()
        self.move(screen.center()-self.rect().center())
        self.clock.start(); self.timer.start(); self.setFocus()

    def tick(self):
        if self.clock.elapsed() >= self.DURATION_MS:
            self.accept()
        else:
            self.update()

    def done(self,result):
        self.timer.stop()
        super().done(result)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Escape,Qt.Key_Space,Qt.Key_Return,Qt.Key_Enter): self.accept()
        else: super().keyPressEvent(event)

    def mousePressEvent(self,event):
        self.accept()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        elapsed=self.clock.elapsed() if self.clock.isValid() else 0
        t=min(1.0,elapsed/self.DURATION_MS)
        p.fillRect(self.rect(),QColor('#070b14'))
        # Original arcade grid; no external video or downloaded assets.
        p.setPen(QPen(QColor('#14283a'),1))
        horizon=310
        for x in range(-760,1521,95): p.drawLine(380,horizon,x,460)
        for y in (310,324,343,369,406,459): p.drawLine(0,y,760,y)
        p.setPen(QPen(QColor('#325a72'),1));p.drawRect(self.rect().adjusted(1,1,-2,-2))
        p.setOpacity(min(1,elapsed/450))
        self.logo.render(p,QRectF(326,56,108,108))
        font=QFont('Consolas',34,QFont.Bold); font.setLetterSpacing(QFont.AbsoluteSpacing,7)
        p.setFont(font);p.setPen(QColor('#edf8ff'))
        p.drawText(QRectF(0,176,760,60),Qt.AlignCenter,'ASCEND')
        p.setFont(QFont('Consolas',12));p.setPen(QColor('#8ad9ed'))
        p.drawText(QRectF(0,237,760,28),Qt.AlignCenter,'P S   C A P T U R E   P R O G R A M')
        p.setOpacity(1)
        bar=QRectF(180,293,400,12);p.fillRect(bar,QColor('#172738'))
        # Segmented arcade loading bar is decorative, not a hardware diagnostic.
        count=int(t*25)
        for i in range(count): p.fillRect(QRectF(182+i*16,295,12,8),QColor('#72ead6'))
        phases=('POWER ON','BOOTING ASCEND','PREPARING YOUR WORKSPACE','READY TO CAPTURE')
        phase=min(3,int(t*4))
        p.setFont(QFont('Consolas',11));p.setPen(QColor('#c8e8ed'))
        p.drawText(QRectF(0,325,760,28),Qt.AlignCenter,phases[phase]+('  _' if elapsed//350%2==0 else ''))
        p.setFont(QFont('Consolas',10));p.setPen(QColor('#9cb3c8'))
        p.drawText(QRectF(0,409,760,26),Qt.AlignCenter,'CLICK OR PRESS SPACE / ENTER / ESC TO SKIP')
        # Low-contrast static scanlines, without flashing or expensive effects.
        p.setPen(QColor(0,0,0,28))
        for y in range(0,460,4):p.drawLine(0,y,760,y)
        p.end()
