# Installed by install.py; source this at the end of .zshrc.
# Keep all theme settings in the Python program's configuration file.
# Give Qt applications launched from this shell the shared platform palette
# only after chthm has enabled its managed qt6ct environment entry.
if (( $+commands[qt6ct] )) &&
   [[ -r "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-chthm-qt6ct.conf" ]]; then
    export QT_QPA_PLATFORMTHEME=qt6ct
fi

chthm() {
    emulate -L zsh
    local output arg
    for arg in "$@"; do
        case "$arg" in
            -h|--help|--version)
                command chthm "$@"
                return $?
                ;;
        esac
    done
    output=$(COLUMNS=$COLUMNS command chthm --shell "$@") || return $?
    eval "$output"
}

# Read palette exports only; startup performs no writes or application reloads.
if (( $+commands[chthm] )); then
    eval "$(command chthm exports)"
fi
