import logging

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant import config_entries
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
import homeassistant.util.dt as dt_util
from homeassistant.helpers import device_registry as dr

from . import pyplejd

_LOGGER = logging.getLogger(__name__)

DOMAIN = "plejd"

async def async_setup(hass, config):
    if not hass.config_entries.async_entries("plejd"):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                "plejd", context={"source": config_entries.SOURCE_IMPORT}, data={}
            )
        )

    return True


async def async_setup_entry(hass, config_entry):

    plejdManager = pyplejd.PlejdManager(config_entry.data)

    devices = await plejdManager.get_devices()
    scenes = await plejdManager.get_scenes()

    # Add a service entry if there are no devices - just so the user can get diagnostics data
    if sum(d.type in ["light", "switch"] for d in devices.values()) == 0:
        site_data = await plejdManager.get_site_data()

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, config_entry.data["siteId"])},
            manufacturer="Plejd",
            name=site_data.get("site", {}).get("title", "Unknown site"),
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    hass.data.setdefault(DOMAIN, {}).update(
        {
            "stopping": False,
        }
    )
    hass.data[DOMAIN].setdefault("devices", {}).update({
        config_entry.entry_id: devices
        })
    hass.data[DOMAIN].setdefault("scenes", {}).update({
        config_entry.entry_id: scenes
        })
    hass.data[DOMAIN].setdefault("manager", {}).update({
        config_entry.entry_id: plejdManager,
    })

    # Close any stale connections that may be open
    for dev in devices.values():
        ble_device = bluetooth.async_ble_device_from_address(
            hass, dev.BLE_address, True
        )
        if ble_device:
            await plejdManager.close_stale(ble_device)

    # Search for devices in the mesh
    def _discovered_plejd(service_info, *_):
        plejdManager.add_mesh_device(service_info.device)
    bluetooth.async_register_callback(
            hass,
            _discovered_plejd,
            BluetoothCallbackMatcher(
                    connectable=True,
                    service_uuid=pyplejd.const.PLEJD_SERVICE.lower()
                ),
            bluetooth.BluetoothScanningMode.PASSIVE
        )

    # Run through already discovered devices and add plejds to the mesh
    for service_info in bluetooth.async_discovered_service_info(hass, True):
        if pyplejd.PLEJD_SERVICE.lower() in service_info.advertisement.service_uuids:
            plejdManager.add_mesh_device(service_info.device)
    

    await hass.config_entries.async_forward_entry_setups(config_entry,
            ["light", "switch", "button"]
        )

    # Ping mesh intermittently to keep the connection alive
    async def _ping(now=None):
        if hass.data[DOMAIN]["stopping"]: return
        if not await plejdManager.keepalive():
            _LOGGER.debug("Ping failed")
        hass.data[DOMAIN]["ping_timer"] = async_track_point_in_utc_time(
                hass,
                _ping,
                dt_util.utcnow() + plejdManager.keepalive_interval
            )
    hass.async_create_task(_ping())

    # Cleanup when Home Assistant stops
    async def _stop(ev):
        hass.data[DOMAIN]["stopping"] = True
        if "ping_timer" in hass.data[DOMAIN]:
            hass.data[DOMAIN]["ping_timer"]()
        await plejdManager.disconnect()
    config_entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    )
    
    return True
