"""
MaFile → steam_guard для SteamClient.
JSON часто даёт Session.SteamID числом; guard/HTTP ожидают str.
"""


class MafileSteamGuard:
    """Сборка словаря steam_guard из maFile с нормализацией SteamID в str."""

    @staticmethod
    def build_dict(ma_data: dict, login: str) -> dict:
        steamid_raw = ma_data.get("Session", {}).get("SteamID")
        shared_secret = ma_data.get("shared_secret")
        identity_secret = ma_data.get("identity_secret")

        if steamid_raw is None or not shared_secret or not identity_secret:
            raise ValueError(
                f"maFile для {login} не содержит необходимых полей (steamid/shared_secret/identity_secret)"
            )

        return {
            "steamid": str(steamid_raw),
            "shared_secret": shared_secret,
            "identity_secret": identity_secret,
        }
