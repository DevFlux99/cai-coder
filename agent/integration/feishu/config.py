import os


class FeishuBotConfig:
    """Feishu bot configuration"""

    # Feishu app credentials
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

    # Session configuration
    SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))  # Session timeout in seconds, default 1 hour

    @classmethod
    def validate(cls):
        """Validate that the configuration is complete"""
        if not cls.FEISHU_APP_ID or not cls.FEISHU_APP_SECRET:
            raise ValueError("FEISHU_APP_ID and FEISHU_APP_SECRET must be configured")