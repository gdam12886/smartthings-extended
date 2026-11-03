# SmartThings Extended

Use Samsung cooktops, connected hoods, and ovens in Home Assistant through your existing native SmartThings connection. Version 0.3.0 adds oven clock synchronization alongside appliance controls and sensors, including separate entities for each oven cavity.

## Requirements

- Home Assistant 2026.9.3 or newer.
- The native SmartThings integration configured and working.
- A Samsung cooktop or oven that exposes the capabilities listed below through SmartThings.

Samsung cloud access is still required. SmartThings Extended shares the native integration's authenticated client and push connection; it does not ask for a separate token or create a second cloud subscription.

## Install with HACS

1. Open **HACS** > the three-dot menu > **Custom repositories**.
2. Add `https://github.com/gdam12886/smartthings-extended` with type **Integration**.
3. Download **SmartThings Extended** and restart Home Assistant.
4. Open **Settings** > **Devices & services** > **Add integration** and select **SmartThings Extended**.
5. Select your native SmartThings account, your cooktop and/or oven, and the feature groups you want. Select **Appliance controls and sensors** for the cooktop and oven features.

You can change devices, feature groups, and the maximum hood timer duration through the integration's options. Each selected appliance appears under SmartThings Extended with its own entities and device page.

**Upgrading from 0.1.0:** update in HACS and restart Home Assistant. Open **Settings > Devices & services > SmartThings Extended > Configure**, select both appliances, and enable **Appliance controls and sensors** alongside your existing hood feature groups. Upgrading preserves your existing selections and hood entity IDs; it does not automatically select additional devices or features.

For manual installation, copy `custom_components/smartthings_extended` into your Home Assistant `custom_components` directory and restart Home Assistant.

## Features

Entities are created from capabilities actually returned by the selected device. Missing capabilities do not produce placeholder controls or zero readings. Reported null values stay unknown. Appliance capabilities marked disabled by Samsung are unavailable; the verified cooktop hood lamp and fan are an exception to Samsung's disabled flags.

### Cooktop and oven

| Capability | Entities and behavior |
| --- | --- |
| Cooktop power | Power switch and power-status sensor, independent of the hood fan switch. |
| Cooktop operation | Reported operating state and cooking/running sensor. |
| Oven mode | Standard and Samsung mode sensors for each component. Mode selectors appear only when that component reports a nonempty supported-mode list. |
| Oven operation | Machine state, job state, completion time, progress, and operation time for each component. Units come from the device; operation time without a unit is shown without an assumed unit. |
| Oven commands | Stop per component. Start appears only when the component reports a supported running state and its current standard mode is in its supported-mode list. Start uses that reported mode without inventing a temperature or cooking duration. |
| Oven clock | Sync clock button for Samsung ovens with an enabled `execute` capability. Sends Home Assistant's current local time. |
| Door and cavities | Door-open sensors and cavity-active status where exposed. Cavity controls are unavailable while their reported cavity status is off. |
| Child lock | Lock-state sensor and locked indicator. Lock/unlock controls appear only when the separate child-lock control capability is enabled. |
| Energy and power meters | Meter sensors only when the device returns those capabilities, with its reported values and units. |
| Software | Software/firmware versions, driver version, update availability/state/progress, and last-update date where exposed. Firmware installation is not implemented. |
| Refresh | Manual refresh button where supported. Normal updates use the native push stream. |

Controls honor a reported remote-control restriction. Power-off and oven-stop remain available when remote start is disabled. An offline device or an unavailable native connection makes its entities unavailable.

Oven components use Samsung's component names, such as **Cavity 2** and **Cavity 3**. The integration does not assume which cavity is upper or lower. Mode selectors and start buttons can appear later if the device begins reporting the required support data.

### Oven clock synchronization

Select **Appliance controls and sensors**, then open the oven's device page and press **Sync clock** under **Configuration**. Each press uses Home Assistant's configured time zone and current daylight-saving rules. Samsung expects the local wall-clock date/time without a timezone suffix.

There is one clock button per oven, rather than one per cavity. It can also be used with the standard `button.press` action in a Home Assistant automation, for example for a daily sync or after a Home Assistant restart:

```yaml
actions:
  - action: button.press
    target:
      entity_id: button.oven_sync_clock
```

Use your actual entity ID. Synchronization runs when the button is pressed or an automation calls it. The integration does not create a schedule. The button's timestamp records the request; check the oven display to verify the first sync because the integration does not read back its clock.

Clock synchronization uses the Samsung `/configuration/vs/0` execute resource documented by [samsung-oven-sync-time](https://github.com/nomis/samsung-oven-sync-time). It is separate from the supported cooking-mode lists and does not require remote cooking control to be enabled. Samsung firmware support for this resource can vary.

### Connected hood

- **Hood light:** on/off using the lamp capability, independently of the fan switch.
- **Hood fan:** on/off and percentage speeds derived from the device's reported positive speed list. Zero always means off.
- **Hood timer duration:** set the actual native countdown duration in minutes.
- **Start hood timer / Cancel hood timer:** start or cancel the hood's timer. Turn on the fan and set a positive duration before starting it. Cancel sends only the timer-cancel command.
- **Hood timer status / Hood timer remaining:** actual reported timer values, with durations normalized to minutes. These are not a separate Home Assistant timer.
- **Hood connection:** show whether the cooktop reports its hood connected.

The timer's maximum input is a configurable Home Assistant UI limit, initially 60 minutes; it is not a manufacturer-specified limit. Set it to the range supported by your hood. The device remains responsible for accepting commands and reporting its actual state.

Unknown timer values remain unknown. A hood disconnection makes its controls unavailable. If the native SmartThings integration reloads, the extension detaches from its old client and reconnects to the replacement client. It reads a fresh status snapshot when connecting and then uses push events, without continuous REST polling.

## Moving existing devices and controls

This integration creates new appliance entity IDs and keeps the 0.1.0 hood IDs. Check the new entities and update dashboard/automation references before manually removing old device entries or REST/MQTT configuration. You can disable duplicated native entities. SmartThings may recreate its native device entries when it reconnects.

**Keep the native SmartThings account integration enabled and keep the physical appliances in SmartThings.** It provides the authenticated connection used by SmartThings Extended. Devices that already work well in the native integration can continue using it.

## Samsung API limits

Available features vary by model and firmware. On the cooktop and three-component oven used to develop 0.2.0:

- The cooktop provides power, operating state, hood controls, lock status, and software status. Its child-lock control is disabled, and it currently returns no energy/power meter capability.
- The oven provides mode/operation sensors, door and lock status, software status, cavity status, and stop commands. Its supported-mode and supported-machine-state lists are null, so mode selectors and start buttons are not offered.
- The oven reports no temperature measurement or temperature-setpoint capability. Temperature controls cannot be supplied by this integration for that device.

Internal identification and diagnostic-upload capabilities are not exposed as appliance controls. The clock button sends one specific `execute` operation; there is no arbitrary execution service. Software update metadata is read-only; the integration does not guess firmware-update module identifiers or schedule updates.

## Compatibility and development

Version 0.3.0 implements the appliance capabilities above. It depends on native SmartThings for authentication and events. The native client is accessed through its runtime data; this interface is internal to Home Assistant and may require adaptation when Home Assistant changes it. The adapter is isolated in `native.py`. Tests run against Home Assistant 2026.9.3 and its SmartThings client version.

The extension does not store, copy, or expose the native account's tokens. Diagnostics omit account tokens, device names, and device IDs.

Run tests against the pinned Home Assistant release:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
ruff check .
ruff format --check .
mypy --follow-imports=silent --ignore-missing-imports custom_components/smartthings_extended
pytest -q
```

The fan percentage mapping and SmartThings capability approach are adapted from the native Home Assistant SmartThings integration. See [NOTICE](NOTICE) and [LICENSE](LICENSE).
