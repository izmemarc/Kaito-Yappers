import os
import json
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    """
    A centralized cache manager that stores cache data in a JSON file.
    """
    def __init__(self, filename="cache.json"):
        # Use an absolute path so that the file is always in the same location.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.filename = os.path.join(base_dir, filename)
        self.cache = {}
        self.load_cache()

    def load_cache(self) -> None:
        """
        Loads cache from the file. If the file does not exist, starts with an empty cache.
        """
        if not os.path.exists(self.filename):
            logger.info(f"Cache file {self.filename} does not exist. Starting with an empty cache.")
            self.cache = {}
            return
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                self.cache = json.load(f)
            logger.info(f"Loaded cache from {self.filename} with keys: {list(self.cache.keys())}")
        except Exception as e:
            logger.error(f"Error loading cache from {self.filename}: {str(e)}")
            self.cache = {}

    def write_cache(self) -> None:
        """
        Writes the current in-memory cache to the file.
        """
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"Wrote cache to {self.filename} successfully.")
        except Exception as e:
            logger.error(f"Error writing cache to {self.filename}: {str(e)}")

    def get(self, key, default=None):
        return self.cache.get(key, default)

    def set(self, key, value) -> None:
        self.cache[key] = value
        self.write_cache()

    def clear(self, key=None) -> None:
        """
        Clears a specific key in the cache (or the entire cache if key is None) and writes it to disk.
        """
        if key:
            if key in self.cache:
                del self.cache[key]
                logger.info(f"Cleared cache for key: {key}")
        else:
            self.cache = {}
            logger.info("Cleared entire cache.")
        self.write_cache() 