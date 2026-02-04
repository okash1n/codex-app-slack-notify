on run
  set output to ""
  set procNames to {"NotificationCenter", "UserNotificationCenter"}
  repeat with procName in procNames
    try
      tell application "System Events"
        tell process (procName as text)
          repeat with w in windows
            set textList to {}
            set elems to entire contents of w
            repeat with e in elems
              try
                if (role of e) is "AXStaticText" then
                  set tval to ""
                  try
                    set tval to (value of e)
                  end try
                  if tval is missing value or tval is "" then
                    try
                      set tval to (name of e)
                    end try
                  end if
                  if tval is not missing value and tval is not "" then
                    set end of textList to tval
                  end if
                end if
              end try
            end repeat
            if (count of textList) > 0 then
              set windowLine to ""
              repeat with t in textList
                set windowLine to windowLine & t & tab
              end repeat
              set output to output & windowLine & linefeed
            end if
          end repeat
        end tell
      end tell
    on error errMsg number errNum
      try
        set errPath to POSIX file "/tmp/codex-notify-slack-helper.err"
        set ef to open for access errPath with write permission
        write ((errNum as text) & ": " & errMsg & linefeed) to ef starting at eof
        close access ef
      end try
    end try
  end repeat

  try
    set targetPath to POSIX file "/tmp/codex-notify-slack-notification.txt"
    set f to open for access targetPath with write permission
    set eof of f to 0
    write output to f starting at 1
    close access f
  on error
    try
      close access targetPath
    end try
  end try
end run
