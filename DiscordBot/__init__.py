"""
ModelNetBeta/DiscordBot package

This package contains all the modules needed for the Discord bot to function.
"""

# Import main modules to make them available from the package
try:
    from . import utils
    from . import database
    from . import consolidated_commands
    from . import register_consolidated_commands
except ImportError:
    # This allows the modules to be imported individually if not used as a package
    pass 