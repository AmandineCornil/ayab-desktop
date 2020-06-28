# -*- coding: utf-8 -*-
# This file is part of AYAB.
#
#    AYAB is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    AYAB is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with AYAB.  If not, see <http://www.gnu.org/licenses/>.
#
#    Copyright 2013-2020 Sebastian Oliva, Christian Obersteiner,
#    Andreas Müller, Christian Gerbrandt
#    https://github.com/AllYarnsAreBeautiful/ayab-desktop

import logging
import os
import weakref
# from copy import copy
from time import sleep
import serial.tools.list_ports
from PIL import ImageOps
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import QSettings, QTranslator, QCoreApplication
from PyQt5.QtWidgets import QCheckBox, QSpinBox, QComboBox
from . import ayab_image
from .ayab_options import Ui_DockWidget
from .ayab_control import AYABControl, AYABControlKnitResult, KnittingMode


MACHINE_WIDTH = 200

class AyabPlugin(object):

    def __init__(self):
        self.__ayab_control = AYABControl()
        self.__logger = logging.getLogger(type(self).__name__)

    def __del__(self):
        self.__ayab_control.close()

    def setupUi(self, parent):
        """Sets up UI elements from ayab_options.Ui_DockWidget in parent."""
        self.__parent = parent  # weakref.ref(parent)
        self.__set_translator()
        self.ui = Ui_DockWidget()
        self.dock = parent.ui.knitting_options_dock
        self.ui.setupUi(self.dock)
        self.ui.tabWidget.setTabEnabled(1, False)
        self.ui.label_progress.setText("")
        self.ui.label_direction.setText("")
        self.__setup_behavior()

        # Disable "continuous reporting" checkbox and Status tab for now
        parent.findChild(QCheckBox, "checkBox_ContinuousReporting").setVisible(False)
        parent.findChild(QtWidgets.QTabWidget, "tabWidget").removeTab(1)

    def __set_translator(self):
        app = QtCore.QCoreApplication.instance()
        self.translator = QTranslator()
        language = self.__parent.prefs.settings.value("language")
        lang_dir = self.__parent.app_context.get_resource("ayab/translations")
        try:
            self.translator.load("ayab_trans." + language, lang_dir)
        except (TypeError, FileNotFoundError):
            self.__logger("Unable load translation file for preferred language, using default locale")
            translator.load(QLocale.system(), "ayab_trans", "", lang_dir)
        except:
            self.__logger("Unable to load translation file")
            raise
        app.installTranslator(self.translator)

    def __setup_behavior(self):
        """Connects methods to UI elements."""
        self.__populate_ports()
        self.ui.refresh_ports_button.clicked.connect(self.__populate_ports)
        self.ui.start_needle_edit.valueChanged.connect(self.__emit_needles)
        self.ui.stop_needle_edit.valueChanged.connect(self.__emit_needles)
        self.ui.start_needle_color.currentIndexChanged.connect(self.__emit_needles)
        self.ui.stop_needle_color.currentIndexChanged.connect(self.__emit_needles)
        self.ui.alignment_combo_box.currentIndexChanged.connect(self.__emit_alignment)
        self.ui.start_row_edit.valueChanged.connect(self.__onStartLineChanged)

    def __populate_ports(self, combo_box=None, port_list=None):
        if not combo_box:
            combo_box = self.__parent.findChild(QtWidgets.QComboBox, "serial_port_dropdown")
        if not port_list:
            port_list = self.__get_serial_ports()
        combo_box.clear()
        self.__populate(combo_box, port_list)
        # Add Simulation item to indicate operation without machine
        combo_box.addItem(QCoreApplication.translate("AyabPlugin", "Simulation"))

    def __populate(self, combo_box, port_list):
        for item in port_list:
            # TODO: should display the info of the device.
            combo_box.addItem(item[0])

    def __get_serial_ports(self):
        """
        Returns a list of all USB Serial Ports
        """
        return list(serial.tools.list_ports.grep("USB"))

    def configure(self):
        conf = self.__get_configuration_from_ui(self.__parent)

        # Start to knit with the bottom first
        image = self.__parent.scene.image.rotate(180)

        # Mirroring option
        if conf.get("auto_mirror"):
            image = ImageOps.mirror(image)

        # TODO: detect if previous conf had the same
        # image to avoid re-generating.

        try:
            self.__image = ayab_image.ayabImage(image, self.conf["num_colors"])
        except:
            self.__emit_popup("You need to set an image.", "error")
            return

        valid = self.__validate_configuration(conf)
        if valid:
            if conf.get("start_needle") and conf.get("stop_needle"):
                self.__image.setKnitNeedles(conf.get("start_needle"),
                                            conf.get("stop_needle"))
            if conf.get("alignment"):
                self.__image.setImagePosition(conf.get("alignment"))

            self.__image.setStartLine(conf.get("start_line"))
            self.__emit_progress(conf.get("start_line") + 1,
                                 self.__image.imgHeight(), 0, "")
            self.__parent.signalConfigured.emit()

    def __get_configuration_from_ui(self, ui):
        """Creates a configuration dict from the UI elements.

    Returns:
      dict: A dict with configuration.

    """
        self.conf = {}
        continuousReporting = ui.findChild(
            QCheckBox, "checkBox_ContinuousReporting").isChecked()
        if continuousReporting == 1:
            self.conf["continuousReporting"] = True
        else:
            self.conf["continuousReporting"] = False

        color_line_text = ui.findChild(QSpinBox, "color_edit").value()
        self.conf["num_colors"] = int(color_line_text)

        # Internally, we start counting from zero
        # (for easier handling of arrays)
        start_line_text = ui.findChild(QSpinBox, "start_row_edit").value()
        self.conf["start_line"] = int(start_line_text) - 1

        start_needle_color = ui.findChild(QComboBox, "start_needle_color").currentText()
        start_needle_text = ui.findChild(QSpinBox, "start_needle_edit").value()

        self.conf["start_needle"] = self.__read_needle_settings(
            start_needle_color, start_needle_text)

        stop_needle_color = ui.findChild(QComboBox, "stop_needle_color").currentText()
        stop_needle_text = ui.findChild(QSpinBox, "stop_needle_edit").value()

        self.conf["stop_needle"] = self.__read_needle_settings(
            stop_needle_color, stop_needle_text)

        alignment_text = ui.findChild(QComboBox, "alignment_combo_box").currentText()
        self.conf["alignment"] = alignment_text

        self.conf["inf_repeat"] = \
            int(ui.findChild(QCheckBox, "infRepeat_checkbox").isChecked())

        self.conf["auto_mirror"] = \
            int(ui.findChild(QtWidgets.QCheckBox, "autoMirror_checkbox").isChecked())

        knitting_mode_index = ui.findChild(QComboBox, "knitting_mode_box").currentIndex()
        self.conf["knitting_mode"] = knitting_mode_index

        serial_port_text = ui.findChild(QComboBox, "serial_port_dropdown").currentText()
        self.conf["portname"] = str(serial_port_text)

        # getting file location from textbox
        filename_text = ui.findChild(QtWidgets.QLineEdit, "filename_lineedit").text()
        self.conf["filename"] = str(filename_text)

        self.__logger.debug(self.conf)
        # Add more config options.
        return self.conf

    def __read_needle_settings(self, color, needle):
        '''Reads the Needle Settings UI Elements and normalizes'''
        if (color == "orange"):
            return MACHINE_WIDTH // 2 - int(needle)
        elif (color == "green"):
            return MACHINE_WIDTH // 2 - 1 + int(needle)

    def __validate_configuration(self, conf):
        if conf.get("start_needle") and conf.get("stop_needle"):
            if conf.get("start_needle") > conf.get("stop_needle"):
                self.__emit_popup("Invalid needle start and end.", "warning")
                return False

        if conf.get("start_line") > self.__image.imgHeight():
            self.__emit_popup("Start row is larger than the image.")
            return False

        if conf.get("portname") == '':
            self.__emit_popup("Please choose a valid port.")
            return False

        if conf.get("knitting_mode") == KnittingMode.SINGLEBED.value \
                and conf.get("num_colors") >= 3:
            self.__emit_popup(
                "Singlebed knitting currently supports only 2 colors.",
                "warning")
            return False

        if conf.get("knitting_mode") == KnittingMode.CIRCULAR_RIBBER.value \
                and conf.get("num_colors") >= 3:
            self.__emit_popup("Circular knitting supports only 2 colors.",
                               "warning")
            return False

        return True

    def knit(self):
        if self.conf["continuousReporting"] is True:
            self.ui.tabWidget.setCurrentIndex(1)
        self.__canceled = False
        while True:
            # knit next row
            result = self.__ayab_control.knit(self.__image, self.conf)
            self.__knit_feedback_handler(result)
            # do not need to make copy of progress object to emit to UI thread
            # because signalUpdateKnitProgress connection blocks this thread
            # progress = copy(self.__ayab_control.get_progress())
            progress = self.__ayab_control.get_progress()
            row_mult = self.__ayab_control.get_row_multiplier()
            self.__knit_progress_handler(progress, row_mult)
            if self.__canceled or result is AYABControlKnitResult.FINISHED:
                break
        self.__logger.info("Finished knitting.")
        self.__ayab_control.close()

        # small delay to finish printing to knit progress window
        # before "finish.wav" sound plays
        sleep(1)

        self.__parent.signalDoneKnitting.emit(not self.__canceled)

    def __knit_feedback_handler(self, result):
        if result is AYABControlKnitResult.CONNECTING_TO_MACHINE:
            self.__emit_notification("Connecting to machine...")

        if result is AYABControlKnitResult.WAIT_FOR_INIT:
            self.__emit_notification(
                "Please start machine. (Set the carriage to mode KC-I " +
                "or KC-II and move the carriage over the left turn mark).")

        if result is AYABControlKnitResult.ERROR_WRONG_API:
            self.__emit_popup(
                "Wrong Arduino firmware version. " +
                "Please check that you have flashed " +
                "the latest version. (" + str(self.__ayab_control.API_VERSION) + ")")

        if result is AYABControlKnitResult.PLEASE_KNIT:
            self.__emit_notification("Please knit")
            self.__emit_playsound("start")

        if result is AYABControlKnitResult.DEVICE_NOT_READY:
            self.__emit_notification()
            self.__emit_blocking_popup("Device not ready, try again.")

        if result is AYABControlKnitResult.FINISHED:
            self.__emit_notification(
                "Image transmission finished. Please knit until you " +
                "hear the double beep sound.")

    def __knit_progress_handler(self, progress, row_multiplier):
        self.__emit_progress(progress.current_row,
                             progress.total_rows,
                             progress.repeats,
                             progress.colorSymbol)
        self.__emit_status(progress.hall_l,
                           progress.hall_r,
                           progress.carriage_type,
                           progress.carriage_position)
        self.__emit_knit_progress(progress, row_multiplier)

    def cancel(self):
        self.__emit_notification("Knitting canceled.")
        self.__canceled = True

    # never called
    # def fail(self):
    #     # TODO add message info from event
    #     self.__logger.error("Error while knitting.")
    #     self.__ayab_control.close()

    def setImageDimensions(self, width, height):
        """Called by Main UI on loading of an image to set Start/Stop needle
        to image width. Updates the maximum value of the Start Line UI element"""
        left_side = width // 2
        self.ui.start_needle_edit.setValue(left_side)
        self.ui.stop_needle_edit.setValue(width - left_side)
        self.ui.start_row_edit.setMaximum(height)

    def cleanup_ui(self, parent):
        """Cleans up UI elements inside knitting option dock."""
        # dock = parent.knitting_options_dock
        dock = self.dock
        cleaner = QtCore.QObjectCleanupHandler()
        cleaner.add(dock.widget())
        self.__qw = QtWidgets.QWidget()
        dock.setWidget(self.__qw)
        self.__unset_translator()

    def __unset_translator(self):
        app = QtCore.QCoreApplication.instance()
        app.removeTranslator(self.translator)

    def __emit_blocking_popup(self, message="", message_type="info"):

        """
        Sends the signalDisplayBlockingPopUp QtSignal
        to main GUI thread, blocking it.
        """
        # print(message)
        self.__parent.signalDisplayBlockingPopUp.emit(
            QCoreApplication.translate("AyabPlugin", message), message_type)

    def __emit_popup(self, message="", message_type="info"):
        """
        Sends the signalDisplayPopUp QtSignal
        to main GUI thread, not blocking it.
        """
        # print(message)
        self.__parent.signalDisplayPopUp.emit(
            QCoreApplication.translate("AyabPlugin", message), message_type)

    def __emit_notification(self, message=""):
        """Sends the signalUpdateNotification signal"""
        # print(message)
        self.__parent.signalUpdateNotification.emit(
            QCoreApplication.translate("AyabPlugin", message))

    def __emit_knit_progress(self, progress, row_multiplier):
        """Sends the updateKnitProgress QtSignal."""
        self.__parent.signalUpdateKnitProgress.emit(progress, row_multiplier)

    def __emit_progress(self, row, total=0, repeats=0, colorSymbol=""):
        """Sends the updateProgressBar QtSignal."""
        self.__parent.signalUpdateProgressBar.emit(row, total, repeats, colorSymbol)

    def __emit_status(self, hall_l, hall_r, carriage_type, carriage_position):
        """Sends the updateStatus QtSignal"""
        self.__parent.signalUpdateStatus.emit(hall_l, hall_r, carriage_type,
                                                 carriage_position)

    def __emit_needles(self):
        """Sends the signalUpdateNeedles QtSignal."""

        start_needle_text = self.ui.start_needle_edit.value()
        start_needle_color = self.ui.start_needle_color.currentText()
        start_needle = self.__read_needle_settings(start_needle_color,
                                               start_needle_text)

        stop_needle_text = self.ui.stop_needle_edit.value()
        stop_needle_color = self.ui.stop_needle_color.currentText()
        stop_needle = self.__read_needle_settings(stop_needle_color,
                                              stop_needle_text)

        self.__parent.signalUpdateNeedles.emit(start_needle, stop_needle)

    def __emit_alignment(self):
        """Sends the signalUpdateAlignment QtSignal"""
        alignment_text = self.ui.alignment_combo_box.currentText()
        self.__parent.signalUpdateAlignment.emit(alignment_text)

    def __emit_playsound(self, event):
        # blocking connection means that thread waits until sound has finished playing
        self.__parent.signalPlaysound.emit(event)

    def __onStartLineChanged(self):
        """ """
        start_row_edit = self.ui.start_row_edit.value()
        total_rows = self.__parent.scene.image.size[1]
        self.__emit_progress(start_row_edit, total_rows, 0, "")

