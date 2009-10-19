# Copyright (c) 2007 Mitchell N. Charity
# Copyright (c) 2009, Walter Bender
#
# This file is part of Ruler.
#
# Ruler is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ruler is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ruler.  If not, see <http://www.gnu.org/licenses/>

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import cairo
import os.path

import sugar
from sugar.activity import activity
try: # 0.86+ toolbar widgets
    from sugar.bundle.activitybundle import ActivityBundle
    from sugar.activity.widgets import ActivityToolbarButton
    from sugar.activity.widgets import StopButton
    from sugar.graphics.toolbarbox import ToolbarBox
    from sugar.graphics.toolbarbox import ToolbarButton
except ImportError:
    pass
from sugar.graphics.toolbutton import ToolButton
from sugar.graphics.menuitem import MenuItem
from sugar.graphics.icon import Icon
from sugar.datastore import datastore
try:
    from sugar.graphics import style
    GRID_CELL_SIZE = style.GRID_CELL_SIZE
except:
    GRID_CELL_SIZE = 0

import logging
_logger = logging.getLogger("ruler-activity")

from gettext import gettext as _

import util
import show_rulers
import show_grids
import show_checkers
import show_angles

SERVICE = 'org.sugarlabs.RulerActivity'
IFACE = SERVICE
PATH = '/org/augarlabs/RulerActivity'

# Create a GTK+ widget on which we will draw using Cairo
class MyCanvas(gtk.DrawingArea):

    def __init__(self):
        gtk.DrawingArea.__init__(self)
        self._draw_ruler = False
        self._object = None
        self.connect('expose-event', self.__expose_event_cb)
        self.dpi = 200

    def __expose_event_cb(self, drawing_area, event):
        cr = self.window.cairo_create()

        if self._draw_ruler:
            # draw lines to create a star
            self._object.draw(cr,self._dpi)

        # Restrict Cairo to the exposed area; avoid extra work
        cr.rectangle(event.area.x, event.area.y,
                     event.area.width, event.area.height)
        cr.clip()

    def add_a_ruler(self,r):
        self._draw_ruler = True
        self._object = r
        self.queue_draw()     

    def get_dpi(self):
        return self._dpi

    def set_dpi(self, dpi):
        self._dpi = dpi


#
# Sugar activity
#
class RulerActivity(activity.Activity):

    def __init__(self, handle):
        super(RulerActivity,self).__init__(handle)

        _font = 'helvetica 12'
        _font_bold = 'helvetica bold 12'

        #
        # We need a canvas
        #
        self._canvas = MyCanvas()
        self.set_canvas(self._canvas)
        self._canvas.show()

        _width = gtk.gdk.screen_width()
        _height = gtk.gdk.screen_height()-GRID_CELL_SIZE

        # Read the dpi from the Journal
        try:
            dpi = self.metadata['dpi']
            _logger.debug("Read dpi: " + str(dpi))
            self._canvas.set_dpi(int(dpi))
        except:
            if os.path.exists('/sys/power/olpc-pm'):
                self._canvas.set_dpi(200) # OLPC XO
            else:
                self._canvas.set_dpi(100) # Just a guess

        # Create instances of our graphics
        self._r = show_rulers.ScreenOfRulers(_font,_font_bold,_width,_height)
        self._gcm = show_grids.ScreenGrid_cm(_font,_font_bold,_width,_height)
        self._gmm = show_grids.ScreenGrid_mm(_font,_font_bold,_width,_height)
        self._a90 = show_angles.Angles90(_font,_font_bold,_width,_height)
        self._a360 = show_angles.Angles360(_font,_font_bold,_width,_height)
        self._c = show_checkers.ScreenOfCircles(_font,_font_bold,_width,_height)

        # start with a ruler
        self._current = self._r
        self._canvas.add_a_ruler(self._current)

        # other settings
        self._grids_mode = "cm"
        self._angles_mode = "90"

        #
        # We need some toolbars
        #
        try:
            # Use 0.86 toolbar design
            toolbar_box = ToolbarBox()

            # Buttons added to the Activity toolbar
            activity_button = ActivityToolbarButton(self)
            toolbar_box.toolbar.insert(activity_button, 0)
            activity_button.show()

            # Show rulers
            self.rulers = ToolButton( "ruler" )
            self.rulers.set_tooltip(_('Ruler'))
            self.rulers.props.sensitive = True
            self.rulers.connect('clicked', self._rulers_cb)
            toolbar_box.toolbar.insert(self.rulers, -1)
            self.rulers.show()

            # Show grids
            self.grids = ToolButton( "grid-a" )
            self.grids.set_tooltip(_('Grid'))
            self.grids.props.sensitive = True
            self.grids.connect('clicked', self._grids_cb)
            toolbar_box.toolbar.insert(self.grids, -1)
            self.grids.show()

            # Show angles
            self.angles = ToolButton( "angles-90" )
            self.angles.set_tooltip(_('Angles'))
            self.angles.props.sensitive = True
            self.angles.connect('clicked', self._angles_cb)
            toolbar_box.toolbar.insert(self.angles, -1)
            self.angles.show()

            # Show checker
            self.checker = ToolButton( "checker" )
            self.checker.set_tooltip(_('Checker'))
            self.checker.props.sensitive = True
            self.checker.connect('clicked', self._checker_cb)
            toolbar_box.toolbar.insert(self.checker, -1)
            self.checker.show()

            separator = gtk.SeparatorToolItem()
            separator.show()
            toolbar_box.toolbar.insert(separator, -1)

            dpi = self._canvas.get_dpi()
            self._dpi_spin_adj = gtk.Adjustment(dpi, 72, 200, 2, 32, 0)
            self._dpi_spin = gtk.SpinButton(self._dpi_spin_adj, 0, 0)
            self._dpi_spin_id = self._dpi_spin.connect('value-changed',
                                                       self._dpi_spin_cb)
            self._dpi_spin.set_numeric(True)
            self._dpi_spin.show()
            self.tool_item_dpi = gtk.ToolItem()
            self.tool_item_dpi.add(self._dpi_spin)
            toolbar_box.toolbar.insert(self.tool_item_dpi, -1)
            self.tool_item_dpi.show()

            separator = gtk.SeparatorToolItem()
            separator.props.draw = False
            separator.set_expand(True)
            separator.show()
            toolbar_box.toolbar.insert(separator, -1)

            # The ever-present Stop Button
            stop_button = StopButton(self)
            stop_button.props.accelerator = '<Ctrl>Q'
            toolbar_box.toolbar.insert(stop_button, -1)
            stop_button.show()

            self.set_toolbar_box(toolbar_box)
            toolbar_box.show()

        except NameError:
            # Use pre-0.86 toolbar design
            toolbox = activity.ActivityToolbox(self)
            self.set_toolbox(toolbox)

            self.projectToolbar = ProjectToolbar(self)
            toolbox.add_toolbar( _('Rulers'), self.projectToolbar )

            toolbox.show()
            toolbox.set_current_toolbar(1)

        self.show_all() 

    #
    # Button callbacks
    #
    def _rulers_cb(self, button):
        self._current = self._r
        self._canvas.add_a_ruler(self._current)
        return True

    def _grids_cb(self, button):
        if self._grids_mode == "cm":
            self._current = self._gcm
            self.grids.set_icon("grid-c")
            self._grids_mode = "mm"
        else:
            self._current = self._gmm
            self.grids.set_icon("grid-a")
            self._grids_mode = "cm"
        self._canvas.add_a_ruler(self._current)
        return True

    def _angles_cb(self, button):
        if self._angles_mode == "90":
            self._current = self._a90
            self.angles.set_icon("angles-360")
            self._angles_mode = "360"
        else:
            self._current = self._a360
            self.angles.set_icon("angles-90")
            self._angles_mode = "90"
        self._canvas.add_a_ruler(self._current)
        return True

    def _checker_cb(self, button):
        self._current = self._c
        self._canvas.add_a_ruler(self._current)
        return True

    def _dpi_spin_cb(self, button):
        self._canvas.set_dpi(self._dpi_spin.get_value_as_int())
        self._canvas.add_a_ruler(self._current)
        return

    """
    Write the dpi to the Journal
    """
    def write_file(self, file_path):
        dpi =  self._canvas.get_dpi()
        _logger.debug("Write dpi: " + str(dpi))
        self.metadata['dpi'] = str(dpi)

#
# Project toolbar for pre-0.86 toolbars
#
class ProjectToolbar(gtk.Toolbar):

    def __init__(self, pc):
        gtk.Toolbar.__init__(self)
        self.activity = pc

        # Ruler
        self.activity.rulers = ToolButton( "ruler" )
        self.activity.rulers.set_tooltip(_('Ruler'))
        self.activity.rulers.props.sensitive = True
        self.activity.rulers.connect('clicked', self.activity._rulers_cb)
        self.insert(self.activity.rulers, -1)
        self.activity.rulers.show()

        # Grid
        self.activity.grids = ToolButton( "grid-a" )
        self.activity.grids.set_tooltip(_('Grid'))
        self.activity.grids.props.sensitive = True
        self.activity.grids.connect('clicked', self.activity._grids_cb)
        self.insert(self.activity.grids, -1)
        self.activity.grids.show()

        # Angles
        self.activity.angles = ToolButton( "angles-90" )
        self.activity.angles.set_tooltip(_('Angles'))
        self.activity.angles.props.sensitive = True
        self.activity.angles.connect('clicked', self.activity._angles_cb)
        self.insert(self.activity.angles, -1)
        self.activity.angles.show()

        # Checker
        self.activity.checker = ToolButton( "checker" )
        self.activity.checker.set_tooltip(_('Checker'))
        self.activity.checker.props.sensitive = True
        self.activity.checker.connect('clicked', self.activity._checker_cb)
        self.insert(self.activity.checker, -1)
        self.activity.checker.show()

        separator = gtk.SeparatorToolItem()
        separator.set_draw(True)
        self.insert(separator, -1)
        separator.show()

        dpi = self.activity._canvas.get_dpi()
        self.activity._dpi_spin_adj = gtk.Adjustment(dpi, 72, 200, 2, 32, 0)
        self.activity._dpi_spin = \
            gtk.SpinButton(self.activity._dpi_spin_adj, 0, 0)
        self.activity._dpi_spin_id = self.activity._dpi_spin.connect(
                                    'value-changed', self.activity._dpi_spin_cb)
        self.activity._dpi_spin.set_numeric(True)
        self.activity._dpi_spin.show()
        self.activity.tool_item_dpi = gtk.ToolItem()
        self.activity.tool_item_dpi.add(self.activity._dpi_spin)
        self.insert(self.activity.tool_item_dpi, -1)
        self.activity.tool_item_dpi.show()

