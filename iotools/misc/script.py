from __future__ import annotations

import pathlib
from contextlib import contextmanager
import functools
import traceback
from typing import Dict, Any, Callable
import inspect
import os

from maybe import Maybe
from subtypes import DateTime, Enum
from pathmagic import Dir, PathLike
from miscutils import Timer, executed_within_user_tree, ReprMixin

from .log import PrintLog
from ..handler.iohandler import RunMode


class FunctionSpec(ReprMixin):
    class FunctionType(Enum):
        INSTANCE, STATIC, CLASS, UNKNOWN = "instance", "static", "class", "unknown"

    def __init__(self, parent: Any, name: str, parent_reference: Any) -> None:
        self.class_, self.name, self.func = parent, f"{parent.__name__}.{name}", parent_reference if (ref_is_func := inspect.isfunction(parent_reference)) else parent_reference.__func__

        if ref_is_func:
            self.type = self.FunctionType.INSTANCE
        elif isinstance(parent_reference, staticmethod):
            self.type = self.FunctionType.STATIC
        elif isinstance(parent_reference, classmethod):
            self.type = self.FunctionType.CLASS
        else:
            self.type = self.FunctionType.UNKNOWN

        self.is_static = self.type == self.FunctionType.STATIC
        self.is_instance = self.type == self.FunctionType.INSTANCE
        self.is_class = self.type == self.FunctionType.CLASS
        self.is_bound = self.is_instance or self.is_class

    def wrap(self, func: Callable) -> Any:
        if self.is_instance:
            half_wrapped = func
        elif self.is_static:
            half_wrapped = staticmethod(func)
        elif self.is_class:
            half_wrapped = classmethod(func)
        else:
            raise ValueError(f"Don't know function type of {self}.")

        return functools.wraps(self.func)(half_wrapped)


class NestedPrintLog(PrintLog):
    def __init__(self, path: PathLike, active: bool = True, to_stream: bool = True, to_file: bool = True, indentation_token: str = "    ") -> None:
        super().__init__(path=path, active=active, to_stream=to_stream, to_file=to_file)
        self.indentation_token, self.indentation_level = indentation_token, 0

    def write(self, text: str, to_stream: bool = None, to_file: bool = None, add_newlines: int = 0) -> None:
        """Write the given text to this log's file and to sys.stdout, based on the 'to_console' and 'to_file' attributes set by the constructor. These attributes can be overriden by the arguments in this call."""
        if Maybe(to_stream).else_(self.to_stream):
            super().write(text, to_stream=True, to_file=False, add_newlines=add_newlines)

        if Maybe(to_file).else_(self.to_file):
            prefix = f"{DateTime.now().to_logformat()} - {self.indentation_token*self.indentation_level}"
            new_text = "\n".join(f"{prefix}{line}" if line else "" for line in text.split("\n"))
            super().write(text=new_text, to_stream=False, to_file=True, add_newlines=add_newlines)

    @contextmanager
    def indentation(self) -> NestedPrintLog:
        self.indentation_level += 1
        yield self
        self.indentation_level -= 1

    @contextmanager
    def reset_output_channels_soon(self) -> NestedPrintLog:
        to_stream, to_file = self.to_stream, self.to_file
        yield self
        self.to_stream, self.to_file = to_stream, to_file


class ScriptProfiler:
    """A profiler decorator class used by the Script class."""

    def __init__(self, log: NestedPrintLog = None, verbose: bool = False) -> None:
        self.log, self.verbose = log, verbose

    def __call__(self, spec: FunctionSpec = None) -> Callable:
        def script_wrapper(*args: Any, **kwargs: Any) -> Any:
            instance = args[0] if spec.is_instance else None
            positional, keyword = ', '.join([repr(arg) for arg in args[1 if spec.is_bound else 0:]]), ', '.join([f'{name}={repr(val)}' for name, val in kwargs.items()])
            arguments = f"{positional}{f', ' if positional and keyword else ''}{keyword}"

            with self.log.reset_output_channels_soon():
                with self.log(to_stream=self.verbose):
                    print(f"{spec.name}({arguments}) starting...")

                timer = Timer()

                with self.log(to_stream=True):
                    with self.log.indentation():
                        ret = spec.func(*args, **kwargs)

                with self.log(to_stream=self.verbose):
                    has_repr = spec.class_.__repr__ is not object.__repr__
                    print(f"{spec.name} finished in {timer} seconds, returning: {repr(ret)}.{f' State of the {spec.class_.__name__} object is: {repr(instance)}' if spec.is_instance and has_repr else ''}")

            return ret

        return spec.wrap(script_wrapper)


class ScriptMeta(type):
    """The metaclass driving the Script class' magic behaviour."""

    def __init__(cls, name: str, bases: Any, namespace: dict) -> None:
        profiler = ScriptProfiler(verbose=namespace.get("verbose", False))
        cls.name, cls._profiler = os.path.splitext(os.path.basename(os.path.abspath(inspect.getfile(cls))))[0], profiler

        cls._recursively_wrap(item=cls)
        cls.__init__ = cls._constructor_wrapper(cls.__init__)

    def _recursively_wrap(cls, item: Any) -> None:
        for name, val in vars(item).items():
            if cls._is_valid_function_type(val) and (name == "__init__" or not (name.startswith("__") and name.endswith("__"))):
                setattr(item, name, cls._profiler(FunctionSpec(parent=item, name=name, parent_reference=val)))

            elif inspect.isclass(val):
                cls._recursively_wrap(item=val)

    def _constructor_wrapper(cls, func: Callable) -> Callable:
        @functools.wraps(func)
        def init_wrapper(script: Script, *args, **kwargs: Any) -> None:
            script.arguments = kwargs

            if (log_location := pathlib.Path(script.log_location)).is_absolute():
                logs_dir = Dir(log_location)
            else:
                logs_dir = (Dir.from_home() if executed_within_user_tree() else Dir.from_root()).join_dir(log_location)

            now = DateTime.now()
            log_path = logs_dir.new_dir(now.to_isoformat(time=False)).new_dir(script.name).new_file(f"[{now.hour:02d}h {now.minute:02d}m {now.second:02d}s]", "txt")
            script._profiler.log = script.log = NestedPrintLog(log_path)

            exception = None

            try:
                func(script, *args, **kwargs)
            except Exception as ex:
                exception = ex
                script.log.write(traceback.format_exc(), to_stream=False)

            if script.serialize:
                script.log.file.new_rename(script.log.file.stem, "pkl").content = script

            if exception is not None:
                raise exception

        return init_wrapper

    def _is_valid_function_type(cls, candidate: Any) -> bool:
        return inspect.isfunction(candidate) or isinstance(candidate, (staticmethod, classmethod))


class Script(metaclass=ScriptMeta):
    """
    A Script class intended to be subclassed. Acquires a 'Script.name' attribute based on the stem of the file it is defined in.
    Performs detailed logging of the execution of the methods (in a call-stack-aware, argument-aware, return-value-aware manner) defined within the class until the contructor returns.
    All console output will also be logged. The log can be accessed through the 'Script.log' attribute.
    Recommended usage is to write the high-level flow control of the script into the constructor, and call other methods from within it.
    Upon exiting the constructor, the script object itself will be serialized using the pickle protocol.
    """
    name: str
    arguments: Dict[str, Any]
    log: NestedPrintLog

    verbose = serialize = False
    log_location = "/Python/logs"

    def __init__(self, *args, **kwargs: Any) -> None:
        pass

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join([f'{attr}={repr(val)}' for attr, val in self.__dict__.items() if not attr.startswith('_')])})"

    @classmethod
    def exec_prog(cls, **arguments: Any) -> Script:
        return cls(run_mode=RunMode.PROGRAMMATIC, **arguments)

    @classmethod
    def exec_gui(cls, **arguments: Any) -> Script:
        return cls(run_mode=RunMode.GUI, **arguments)

    @classmethod
    def exec_cl(cls, **arguments: Any) -> Script:
        return cls(run_mode=RunMode.COMMANDLINE, **arguments)
