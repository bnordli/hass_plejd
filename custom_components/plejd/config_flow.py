import voluptuous as vol
import logging
from homeassistant.config_entries import ConfigFlow

from .pyplejd import api

_LOGGER = logging.getLogger(__name__)

class PlejdConfigFlow(ConfigFlow, domain="plejd"):

    VERSION = 1

    async def async_step_user(self, info=None):

        if info is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("username"): str,
                        vol.Required("password"): str
                    }
                )
            )
        self.credentials = info
        return await self.async_step_picksite()

    async def async_step_picksite(self, info=None):
        if info is None:
            sites = await api.get_sites(self.credentials["username"], self.credentials["password"])
            return self.async_show_form(
                step_id="picksite",
                data_schema=vol.Schema(
                    {
                        vol.Required("site"): vol.In(
                            {
                                site["site"]["siteId"]: site["site"]["title"]
                                for site in sites
                            }
                        )
                    }
                )
            )
        data={
            "username": self.credentials["username"],
            "password": self.credentials["password"],
            "siteId": info["site"]
        }
        return self.async_create_entry(title="Plejd", data=data)
