from __future__ import annotations

from maybe import Maybe

from iotools.command.argument import (
    Argument,
    StringArgument, BooleanArgument, IntegerArgument, FloatArgument,
    FileArgument, DirArgument,
    DateTimeArgument, DateArgument,
    ListArgument, DictArgument
)

from .base import WidgetHandler
from .frame import HorizontalFrame, VerticalFrame
from .group_box import HorizontalGroupBox, VerticalGroupBox
from .numeric import IntEntry, FloatEntry
from .tab_page import TabPage
from .label import Label
from .button import Button
from .checkbox import Checkbox, CheckBar
from .dropdown import DropDown
from .text import Text, Entry
from .path import FileSelect, DirSelect
from .calendar import Calendar, DateTimeEdit
from .html import HtmlDisplay
from .progress import ProgressBar
from .list import List
from .tree import Tree


class Widget:
    class Frame:
        Horizontal = HorizontalFrame
        Vertical = VerticalFrame

    class GroupBox:
        Horizontal = HorizontalGroupBox
        Vertical = VerticalGroupBox

    class Entry:
        Int = IntEntry
        Float = FloatEntry

    TabPage = TabPage
    Label = Label
    Button = Button
    Checkbox = Checkbox
    CheckBar = CheckBar
    DropDown = DropDown
    Text = Text
    FileSelect = FileSelect
    DirSelect = DirSelect
    Calendar = Calendar
    DateTimeEdit = DateTimeEdit
    HtmlDisplay = HtmlDisplay
    ProgressBar = ProgressBar
    List = List
    Tree = Tree

    @staticmethod
    def from_argument(arg: Argument) -> WidgetHandler:
        if arg.choices is not None:
            handler = DropDown(choices=arg.choices, state=arg.default)
        elif isinstance(arg, DictArgument) and arg.validator.deep_type == (str, bool):
            handler = CheckBar(choices=arg.default)
        elif isinstance(arg, BooleanArgument):
            handler = Checkbox(state=Maybe(arg.default).else_(False))
        elif isinstance(arg, IntegerArgument):
            handler = IntEntry(state=arg.default)
        elif isinstance(arg, FloatArgument):
            handler = FloatEntry(state=arg.default)
        elif isinstance(arg, FileArgument):
            handler = FileSelect(state=arg.default)
        elif isinstance(arg, DirArgument):
            handler = DirSelect(state=arg.default)
        elif isinstance(arg, DateTimeArgument):
            handler = DateTimeEdit(state=arg.default, magnitude=arg.widget_magnitude)
        elif isinstance(arg, DateArgument):
            handler = Calendar(state=arg.default)
        elif isinstance(arg, StringArgument):
            handler = Text(state=arg.default, magnitude=arg.widget_magnitude) if arg.widget_magnitude and arg.widget_magnitude > 1 else Entry(state=arg.default)
        elif isinstance(arg, ListArgument):
            handler = List(state=arg.default, deep_type=arg)
        elif isinstance(arg, DictArgument):
            handler = Tree(state=arg.default)
        else:
            raise TypeError(f"Don't know how to handle {type(arg).__name__}: {arg}")

        return handler.with_argument(arg)
