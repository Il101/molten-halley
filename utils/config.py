import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import get_logger

logger = get_logger(__name__)

# Load .env file for local development
load_dotenv()

def get_config(config_path: str = 'config/config.yaml'):
    """
    Load configuration from YAML file and override with environment variables.
    
    Environment variables should be prefixed with ARBIBOT_ and follow the YAML structure.
    Example: ARBIBOT_TELEGRAM_API_ID overrides telegram.api_id
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Config file {config_path} not found. Using defaults/env vars.")
        config = {}
    else:
        with open(path, 'r') as f:
            config = yaml.safe_load(f) or {}

    # Override with environment variables
    # Format: ARBIBOT_SECTION_KEY=value
    for env_key, env_val in os.environ.items():
        if env_key.startswith('ARBIBOT_'):
            parts = env_key[8:].lower().split('_')
            
            # Navigate/Create nested dicts
            current = config
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # Try to convert to int/float/bool
                    if env_val.lower() == 'true':
                        env_val = True
                    elif env_val.lower() == 'false':
                        env_val = False
                    else:
                        try:
                            if '.' in env_val:
                                env_val = float(env_val)
                            else:
                                env_val = int(env_val)
                        except ValueError:
                            pass
                    current[part] = env_val
                else:
                    if part not in current or not isinstance(current[part], dict):
                        current[part] = {}
                    current = current[part]

    # Special common overrides for convenience (without prefix)
    if 'TELEGRAM_API_ID' in os.environ:
        if 'telegram' not in config: config['telegram'] = {}
        config['telegram']['api_id'] = os.environ['TELEGRAM_API_ID']
    if 'TELEGRAM_API_HASH' in os.environ:
        if 'telegram' not in config: config['telegram'] = {}
        config['telegram']['api_hash'] = os.environ['TELEGRAM_API_HASH']
    if 'BINGX_API_KEY' in os.environ:
        if 'exchanges' not in config: config['exchanges'] = {}
        if 'bingx' not in config['exchanges']: config['exchanges']['bingx'] = {}
        config['exchanges']['bingx']['api_key'] = os.environ['BINGX_API_KEY']
    if 'BINGX_API_SECRET' in os.environ:
        if 'exchanges' not in config: config['exchanges'] = {}
        if 'bingx' not in config['exchanges']: config['exchanges']['bingx'] = {}
        config['exchanges']['bingx']['api_secret'] = os.environ['BINGX_API_SECRET']
    if 'BYBIT_API_KEY' in os.environ:
        if 'exchanges' not in config: config['exchanges'] = {}
        if 'bybit' not in config['exchanges']: config['exchanges']['bybit'] = {}
        config['exchanges']['bybit']['api_key'] = os.environ['BYBIT_API_KEY']
    if 'BYBIT_API_SECRET' in os.environ:
        if 'exchanges' not in config: config['exchanges'] = {}
        if 'bybit' not in config['exchanges']: config['exchanges']['bybit'] = {}
        config['exchanges']['bybit']['api_secret'] = os.environ['BYBIT_API_SECRET']

    if 'TELEGRAM_SESSION_STRING' in os.environ:
        if 'telegram' not in config: config['telegram'] = {}
        config['telegram']['session_string'] = os.environ['TELEGRAM_SESSION_STRING']

    return config
