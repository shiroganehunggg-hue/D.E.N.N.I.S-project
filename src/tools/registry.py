import importlib
import inspect
import pkgutil
from typing import List

from src.config.settings import Settings
import src.tools as tools_package
from src.tools.base import Tool

SKIP_MODULES = {"base", "manager", "registry"}


def discover_tools() -> List[Tool]:
    """Tự động quét mọi module/tool trong src/tools/, kể cả các package con."""
    discovered = []

    def walk_package(package_name: str, package_path) -> None:
        for _, module_name, is_pkg in pkgutil.iter_modules(package_path):
            if module_name in SKIP_MODULES:
                continue
            if module_name == "run_python" and not Settings.ALLOW_UNSAFE_PYTHON_TOOL:
                continue

            full_module_name = f"{package_name}.{module_name}"
            module = importlib.import_module(full_module_name)

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Tool) and obj is not Tool and getattr(obj, "enabled", True):
                    discovered.append(obj())

            if is_pkg:
                subpackage_path = [p for p in package_path if p.name == module_name] if False else None
                # Resolve the package path explicitly for nested packages.
                submodule = importlib.import_module(full_module_name)
                walk_package(full_module_name, submodule.__path__)

    walk_package("src.tools", tools_package.__path__)
    return discovered
