"""Optional support/v3 accelerator, selected once when the process starts."""
import importlib
import os

MODE = os.environ.get('SINGULARITY_KERNEL', 'auto')
if MODE not in ('auto', 'python', 'rust'):
    raise RuntimeError('SINGULARITY_KERNEL must be auto, python or rust')

accelerator = None
if MODE != 'python':
    try:
        accelerator = importlib.import_module('singularity_native')
    except ModuleNotFoundError as exc:
        if exc.name != 'singularity_native':
            raise
        if MODE == 'rust':
            raise RuntimeError('Rust kernel required; install ./server/native first') from exc
    if accelerator is not None and accelerator.CONTRACT_VERSION != 1:
        raise RuntimeError('Incompatible singularity-native contract; rebuild the native wheel')

BACKEND = 'rust' if accelerator is not None else 'python'
