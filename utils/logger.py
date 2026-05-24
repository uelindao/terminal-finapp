import logging
import os


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger configurado para o FinTerminal.
    Garante que handlers não sejam duplicados em reimportações.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # já inicializado — evita duplicar handlers

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(module)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # --- Console ---
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # --- Arquivo ---
    os.makedirs('logs', exist_ok=True)
    fh = logging.FileHandler('logs/finterminal.log', encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
