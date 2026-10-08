-- ~/.config/xmonad/xmonad.hs
-- minimal gruvbox

import XMonad
import XMonad.Actions.WithAll (killAll)
import XMonad.Hooks.EwmhDesktops (ewmh, ewmhFullscreen)
import XMonad.Hooks.ManageDocks (avoidStruts, docks)
import XMonad.Hooks.ManageHelpers (doCenterFloat, doFullFloat, isDialog)
import XMonad.Hooks.StatusBar (xmonadPropLog')
import XMonad.Layout.Grid (Grid (..))
import XMonad.Layout.NoBorders (Ambiguity (OnlyScreenFloat), lessBorders)
import XMonad.Layout.Renamed (Rename (Replace), renamed)
import XMonad.Layout.Spacing (Border (..), spacingRaw)
import XMonad.Layout.ToggleLayouts (ToggleLayout (..), toggleLayouts)
import XMonad.Util.EZConfig (additionalKeysP)
import XMonad.Util.NamedScratchpad
import XMonad.Util.Run (runProcessWithInput)
import XMonad.Util.SpawnOnce (spawnOnce)

import Control.Monad (forM_, unless, when)
import Data.List (isSuffixOf)
import System.Exit (exitSuccess)
import qualified XMonad.StackSet as W

------------------------------------------------------------------------
-- colors (everforest dark hard; names kept from gruvbox)

bg0h, bg0, bg1, bg3, fg1, fg2, fg4, gray, yellow, red :: String
bg0h   = "#0c1012"
bg0    = "#111618"
bg1    = "#171c1f"
bg3    = "#4f5b58"
fg1    = "#d3c6aa"
fg2    = "#d3c6aa"
fg4    = "#9da9a0"
gray   = "#7a8478"
yellow = "#a7c080"
red    = "#e67e80"

------------------------------------------------------------------------
-- basics

confDir :: String
confDir = "~/.config/xmonad"

myTerminal :: String
myTerminal = "alacritty"

myWorkspaces :: [String]
myWorkspaces = map show [1 .. 5 :: Int]

rofi :: String
rofi = "rofi -theme " ++ confDir ++ "/rofi/gruvbox.rasi"

------------------------------------------------------------------------
-- layouts: windows sit inside the mellow frame (avoidStruts) with 8px gaps
-- everywhere, even with a single window. only real fullscreen (F11, videos)
-- goes edge-to-edge and borderless, covering the frame.

myLayout = avoidStruts . lessBorders OnlyScreenFloat . gaps . toggleLayouts full $ grid ||| tall ||| wide ||| full
  where
    gaps = spacingRaw False (Border 4 4 4 4) True (Border 4 4 4 4) True
    grid = renamed [Replace "grid"] Grid  -- 4 windows -> 2x2 tiles
    tall = renamed [Replace "tall"] $ Tall 1 (3 / 100) (1 / 2)
    wide = renamed [Replace "wide"] . Mirror $ Tall 1 (3 / 100) (1 / 2)
    full = renamed [Replace "full"] Full

------------------------------------------------------------------------
-- scratchpad

scratchRect :: W.RationalRect
scratchRect = W.RationalRect 0.2 0.2 0.6 0.6

scratchpads :: [NamedScratchpad]
scratchpads =
  [ NS "term" (myTerminal ++ " --class scratchpad") (resource =? "scratchpad")
      (customFloating scratchRect)
  ]

-- toggle the popup terminal, re-floating it if it ever got tiled (e.g. by M-t)
toggleScratchTerm :: X ()
toggleScratchTerm = do
  namedScratchpadAction scratchpads "term"
  withWindowSet $ \ws -> forM_ (W.index ws) $ \w -> do
    isScratch <- runQuery (resource =? "scratchpad") w
    when isScratch $ windows (W.float w scratchRect)

-- push a floating window back into tiling, leaving the popup terminal alone
sinkUnlessScratch :: Window -> X ()
sinkUnlessScratch w = do
  isScratch <- runQuery (resource =? "scratchpad") w
  unless isScratch $ windows (W.sink w)

------------------------------------------------------------------------
-- window rules

myManageHook :: ManageHook
myManageHook =
  composeAll
    [ isDialog                     --> doCenterFloat
    , className =? "Pavucontrol"   --> doCenterFloat
    , className =? "Nm-connection-editor" --> doCenterFloat
    , title     =? "Picture-in-Picture"   --> doFloat
    , resource  =? "screensaver"          --> doFullFloat
    ]
    <+> namedScratchpadManageHook scratchpads

------------------------------------------------------------------------
-- tell the shell which layout is showing: mellow.py reads the root
-- window property _MELLOW_LAYOUT and shows an icon in the left bar

myLogHook :: X ()
myLogHook = do
  l <- gets (description . W.layout . W.workspace . W.current . windowset)
  xmonadPropLog' "_MELLOW_LAYOUT" (last (words l))  -- drop modifier prefixes, keep "tall"

------------------------------------------------------------------------
-- startup

myStartup :: X ()
myStartup = do
  spawnOnce ("xrdb -merge " ++ confDir ++ "/config/Xresources && xsetroot -cursor_name left_ptr")
  spawnOnce (confDir ++ "/scripts/wallpaper.sh")
  spawnOnce ("picom --config " ++ confDir ++ "/config/picom.conf")
  spawnOnce ("dunst -config " ++ confDir ++ "/config/dunstrc")
  spawnOnce "$HOME/.local/bin/hidecursor"  -- hide the cursor while typing (~/.local/src/hidecursor)
  spawnOnce ("clipcatd --replace --config " ++ confDir ++ "/config/clipcat/clipcatd.toml")  -- clipboard history
  spawnOnce "fcitx5 -d --replace"  -- input method: Ctrl+Space toggles English/Japanese (hazkey)
  -- the shell: frame, left bar, hover panels (shell/mellow.py). restarted with xmonad
  spawn ("pkill -f '^python3 .*mellow.py'; python3 " ++ confDir ++ "/shell/mellow.py")
  -- screen never blanks; clock + quotes screensaver after 5 idle minutes
  spawn ("pkill -f '^python3 .*screensaver/idle.py'; python3 " ++ confDir ++ "/scripts/screensaver/idle.py")
  -- the old xmobar helpers, in case they are still running from before mellow
  spawn "pkill -f '^python3 .*(fillets|ws-peek|media-card).py'"

------------------------------------------------------------------------
-- actions

-- close every window on every workspace (gracefully, like M-q)
killEverything :: X ()
killEverything = withWindowSet (mapM_ killWindow . W.allWindows)

powerMenu :: X ()
powerMenu = do
  choice <- runProcessWithInput "sh" ["-c", rofi ++ menuFlags] entries
  case words choice of
    [_, "logout"]   -> io exitSuccess
    [_, "reboot"]   -> spawn "systemctl reboot"
    [_, "shutdown"] -> spawn "systemctl poweroff"
    _               -> pure ()
  where
    entries = unlines ["\xF0343  logout", "\xF0709  reboot", "\xF0425  shutdown"]
    menuFlags = " -dmenu -i -no-custom -theme-str 'window {width: 260px;} listview {lines: 3;}'"

------------------------------------------------------------------------
-- keys

myKeys :: [(String, X ())]
myKeys =
  [ -- apps
    ("M-<Return>",   spawn myTerminal)
  , ("M-d",          spawn (rofi ++ " -show drun"))
  , ("M-p",          spawn (rofi ++ " -show drun"))
  , ("M-v",          spawn ("clipcat-menu --config " ++ confDir ++ "/config/clipcat/clipcat-menu.toml"))  -- clipboard history
  , ("M-<Tab>",      spawn (rofi ++ " -modi \"windows:$HOME/.config/xmonad/rofi/windows.sh\" -show windows"))
  , ("M-s",          toggleScratchTerm)
  , ("M-t",          withFocused sinkUnlessScratch)  -- re-tile, but never the popup terminal

    -- closing
  , ("M-q",          kill)
  , ("M-S-q",        killAll)
  , ("M-C-q",        killEverything)

    -- layout
  , ("M-f",          sendMessage ToggleLayout)

    -- shell panels (they also open by hovering the top / right edge)
  , ("M-a",          spawn "pkill -USR1 -f '^python3 .*mellow.py'")  -- dashboard
  , ("M-S-a",        spawn "pkill -USR2 -f '^python3 .*mellow.py'")  -- notifications + session

    -- session
  , ("M-S-r",        spawn "xmonad --recompile && xmonad --restart")
  , ("M-S-e",        powerMenu)

    -- look
  , ("M-S-w",        spawn (confDir ++ "/scripts/wallpaper.sh next"))

    -- notifications
  , ("M-n",          spawn (confDir ++ "/scripts/bar/bell-seen.sh; dunstctl history-pop"))  -- re-show last notification, clear bell dot
  , ("M-S-n",        spawn ("dunstctl close-all; " ++ confDir ++ "/scripts/bar/bell-seen.sh"))  -- dismiss all, clear bell dot

    -- screenshots
  , ("<Print>",      spawn (confDir ++ "/scripts/screenshot.sh"))
  , ("M-<Print>",    spawn (confDir ++ "/scripts/screenshot.sh region"))
  , ("M-S-s",        spawn (confDir ++ "/scripts/screenshot.sh region"))

    -- media
  , ("<XF86AudioRaiseVolume>", spawn "pamixer -i 5")
  , ("<XF86AudioLowerVolume>", spawn "pamixer -d 5")
  , ("<XF86AudioMute>",        spawn "pamixer -t")
  , ("<XF86AudioPlay>",        spawn "playerctl play-pause")
  , ("<XF86AudioNext>",        spawn "playerctl next")
  , ("<XF86AudioPrev>",        spawn "playerctl previous")
  ]

------------------------------------------------------------------------

main :: IO ()
main =
  xmonad
    . ewmhFullscreen
    . ewmh
    . docks
    $ def
      { terminal           = myTerminal
      , modMask            = mod4Mask
      , workspaces         = myWorkspaces
      , borderWidth        = 2
      , normalBorderColor  = bg1
      , focusedBorderColor = yellow
      , focusFollowsMouse  = True
      , layoutHook         = myLayout
      , manageHook         = myManageHook
      , startupHook        = myStartup
      , logHook            = myLogHook
      }
      `additionalKeysP` myKeys
