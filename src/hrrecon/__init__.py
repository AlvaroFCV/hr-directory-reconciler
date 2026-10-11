"""hrrecon: conciliador de solo lectura entre nómina de RR.HH. y un directorio de usuarios.

Read-only reconciler between an HR payroll export and a directory (AD-like) user export.
The tool only reads local CSV/Excel files and writes reports; it never connects to,
or modifies, any system.
"""

__version__ = "0.1.0"
