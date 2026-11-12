# Integrated automation screen catalog

Captured from `emulator-5554` at 1080×1920 on 2026-11-12. Only navigation controls were used during capture.

## Confirmed fixtures

- `battle_alerts.png`: battle screen with persistent bottom dungeon alert and separate cookie/growth/guild alerts.
- `cookie_menu.png`: cookie roster; batch promotion and current-team level-up are both disabled.
- `pet_menu.png`: pet shelter; `모두 받기` is active but was not pressed.
- `growth_menu.png`: breakthrough screen; attack, defense, and health one-level buttons are active with visible coin costs.
- `fame_menu.png`: fame screen; owned value 103 is below cost 140, so level-up is forbidden.
- `guild_entry.png`: guild home with a Help Center alert.
- `guild_help.png`: individual help and `한 번에 돕기` are active; neither was pressed.
- `guild_lab.png`: research support is disabled by cooldown; crystal research donation is active but permanently forbidden.
- `challenge_menu_red_dot.png`: persistent Arena red dot and counters; this red dot must never create a candidate.
- `daily_menu.png`: daily list with remaining counts and the account's orange `SKIP` ad-pass marker on Coin Dungeon.
- `daily_detail.png`: Experience Dungeon detail with zero remaining key attempts; no challenge was started.

## Unsupported no-tap states

- Active cookie batch promotion and active current-team level-up were not naturally available.
- Guild support claim/check-box screen was not identified without entering an action path.
- Active guild research support was unavailable due to its cooldown.
- Fame level-up with sufficient fame was unavailable.
- Crystal-cost Arena refresh timing screen was not opened.

Unsupported states are always classified as no-tap until a real screenshot is captured and added with a failing test.
