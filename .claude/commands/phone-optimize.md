Optimize the connected Android phone for LLM inference performance.

This puts the phone into "LLM service mode" — stops non-essential apps, disables Samsung/Google bloatware, minimizes screen brightness, disables animations, and keeps the screen awake while charging.

## Steps

1. Find the adb binary (check ~/Android/Sdk/platform-tools/adb or PATH)
2. Verify the phone is connected via `adb devices`
3. Verify llama-server is running: `adb shell "ps -A | grep llama-server"`
4. Show BEFORE state: CPU load, memory, battery, temperature, top 5 processes
5. Stop and disable non-essential packages:
   - Samsung: honeyboard, wearable, rubin, smartsuggestions, mcfds, scpm, game.gametools, mateagent, forest, wellbeing, spay, samsungpass, daemonapp, app.spage, themestore, voc, app.notes
   - Google: googlequicksearchbox, apps.messaging, apps.photos, android.tts
   - Other: alert.meserhadash
   - Use `am force-stop` first, then `pm disable-user --user 0` to prevent respawn
6. Kill all background processes: `adb shell "am kill-all"`
7. Disable animations:
   - `settings put global window_animation_scale 0`
   - `settings put global transition_animation_scale 0`
   - `settings put global animator_duration_scale 0`
8. Set stay awake while charging: `settings put global stay_on_while_plugged_in 3`
9. Minimize screen brightness: `settings put system screen_brightness 10`
10. Wait 5 seconds for the system to settle
11. Show AFTER state: CPU load, memory, battery, temperature, top 5 processes
12. Run a quick inference benchmark: send a simple prompt to localhost:8080/v1/chat/completions and measure response time
13. Print a summary table comparing before/after

## Re-enable command

Tell the user they can restore disabled packages later with:
```
adb shell "pm enable <package_name>"
```

Or re-enable all at once by listing disabled packages:
```
adb shell "pm list packages -d" | sed 's/package://' | xargs -I{} adb shell pm enable {}
```
