"""
GeOS Integration Module

Provides interfaces between Visual Audio cartridges and Geometry OS hypervisor.
"""

from .region_executor import GeOSRegionExecutor, run_cartridge_with_geos

__all__ = [
    'GeOSRegionExecutor',
    'run_cartridge_with_geos',
]