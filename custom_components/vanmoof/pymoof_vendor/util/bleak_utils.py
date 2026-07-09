import bleak.backends.characteristic
import bleak.backends.client
from bleak.exc import BleakError


async def get_characteristic(
    gatt_client: bleak.backends.client.BaseBleakClient,
    char_uuid,
) -> bleak.backends.characteristic.BleakGATTCharacteristic:
    # Vendored change: modern bleak (what Home Assistant ships) removed the
    # awaitable get_services(); services are populated on connect and exposed as
    # the `.services` property (backed by bleak-retry-connector's cache here).
    services = gatt_client.services
    service = services.get_service(char_uuid.SERVICE_UUID.value)
    # Vendored change: on a flaky (proxy) connection the GATT table can come up
    # incomplete, so get_service()/get_characteristic() return None. Raise a
    # BleakError instead of crashing with AttributeError, so the coordinator
    # clears the cache and retries with a fresh discovery.
    if service is None:
        raise BleakError(
            f"service {char_uuid.SERVICE_UUID.value} not found (incomplete GATT discovery)"
        )
    characteristic = service.get_characteristic(char_uuid.value)
    if characteristic is None:
        raise BleakError(f"characteristic {char_uuid.value} not found")
    return characteristic


async def write_to_characteristic(
    gatt_client: bleak.backends.client.BaseBleakClient,
    uuid,
    data: bytes,
) -> None:
    characteristic = await get_characteristic(gatt_client, uuid)
    await gatt_client.write_gatt_char(characteristic, data, response=True)


async def read_from_characteristic(
    gatt_client: bleak.backends.client.BaseBleakClient,
    uuid,
) -> bytes:
    characteristic = await get_characteristic(gatt_client, uuid)
    return await gatt_client.read_gatt_char(characteristic)
