# SmartThings Extended

Add selected hood features to Home Assistant using your existing native SmartThings connection. The first release supports Samsung hoods connected through a cooktop: light, fan speed, and the hood's own countdown timer.

## Requirements

- Home Assistant 2026.9.3 or newer.
- The native SmartThings integration configured and working.
- A Samsung cooktop that exposes a `hood` component through SmartThings.

Samsung cloud access is still required. SmartThings Extended shares the native integration's authenticated client and push connection; it does not ask for a separate token or create a second cloud subscription.

## Install with HACS

1. Open **HACS** > the three-dot menu > **Custom repositories**.
2. Add `https://github.com/gdam12886/smartthings-extended` with type **Integration**.
3. Download **SmartThings Extended** and restart Home Assistant.
4. Open **Settings** > **Devices & services** > **Add integration** and select **SmartThings Extended**.
5. Select your native SmartThings account, the cooktop, and the extra features you want.

You can change devices, feature groups, and the maximum timer duration through the integration's options. The selected cooktops appear under SmartThings Extended with only the extra controls you enable. The native integration keeps its own device pages.

For manual installation, copy `custom_components/smartthings_extended` into your Home Assistant `custom_components` directory and restart Home Assistant.

## Features

- **Hood light:** on/off using the lamp capability, independently of the fan switch.
- **Hood fan:** on/off and percentage speeds derived from the device's reported positive speed list. Zero always means off.
- **Hood timer duration:** set the actual native countdown duration in minutes.
- **Start hood timer / Cancel hood timer:** start or cancel the hood's timer. Turn on the fan and set a positive duration before starting it. Cancel sends only the timer-cancel command.
- **Hood timer status / Hood timer remaining:** actual reported timer values, with durations normalized to minutes. These are not a separate Home Assistant timer.
- **Hood connection:** show whether the cooktop reports its hood connected.

The timer's maximum input is a configurable Home Assistant UI limit, initially 60 minutes; it is not a manufacturer-specified limit. Set it to the range supported by your hood. The device remains responsible for accepting commands and reporting its actual state.

Unknown timer values remain unknown. A hood disconnection makes its controls unavailable. If the native SmartThings integration reloads, the extension detaches from its old client and reconnects to the replacement client. It reads a fresh status snapshot when connecting and then uses push events, without continuous REST polling.

## Existing REST or MQTT controls

This integration adds its own entities. If you already have REST, template, or MQTT hood entities, compare the new controls with the old ones before removing the old configuration. Check automations and dashboard references when moving to the new entity IDs. Disable only duplicated features in the relevant integration.

## Compatibility and development

Version 0.1.0 implements the hood features above; it is not a complete replacement for native SmartThings. Additional capabilities can be added in later releases. The native client is accessed through its runtime data; this interface is internal to Home Assistant and may require adaptation when Home Assistant changes it. The adapter is isolated in `native.py`.

The extension does not store, copy, or expose the native account's tokens. Diagnostics omit account tokens, device names, and device IDs.

Run tests against the pinned Home Assistant release:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
ruff check .
ruff format --check .
pytest -q
```

The fan percentage mapping and SmartThings capability approach are adapted from the native Home Assistant SmartThings integration. See [NOTICE](NOTICE) and [LICENSE](LICENSE).
