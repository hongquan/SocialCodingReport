# Social Coding Report

![Social Coding Report Logo](https://quan-images.b-cdn.net/app-icons/vn.ququ.SocialCodingReport.svg)

A modern GTK4 + LibAdwaita application that helps you generate daily reports of your GitHub activity (Issues and Pull Requests). It fetches data from configured repositories and lets you select items to copy as a formatted HTML list.

## Features

- Modern UI: Built with GTK4 and LibAdwaita for a native GNOME experience.
- GitHub Integration: Fetches "Yesterday" or "Today" activity from your specified repositories.
- Filtering: Quickly toggle between yesterday's and today's work.
- Report Generation: Select activities and generate an HTML unordered list for easy pasting into reports or chats.
- Secure: Uses `GITHUB_TOKEN` from your environment.

## Requirements

### System Dependencies

They are listed in *deb-packages.txt* file, under the name of Debian packages. On Debian, Ubuntu and derivates, you can quickly install them with this command:

Bash

```bash
xargs -a deb-packages.txt sudo apt install
```

Fish

```fish
sudo apt install (cat deb-packages.txt)
```

Nushell

```nushell
open --raw deb-packages.txt | lines | sudo apt install ...$in
```

Some Python packages which aid development can be installed with `pip`, and listed in *requirements-dev.txt*. If you want to install them to a virtual environment, remember to create it with `--system-site-packages` flag.

```bash
pip install -r requirements-dev.txt --break-system-packages
```

## Building and Installing

This project uses the Meson build system.

1. Setup the build directory:
  ```bash
  meson setup __build
  ```

2. Compile:
  ```bash
  ninja -C __build
  ```

3. Install:
  ```bash
  # Installs to /usr/local by default or your configured prefix
  sudo meson install -C __build
  ```

## Running the Application

### 1. GitHub Token
The application requires a GitHub Personal Access Token to fetch data. Export it as an environment variable:

```bash
export GITHUB_TOKEN="your_github_token_here"
```

### 2. Launch
After installation, you can run the application directly:

```bash
socialcodingreport
```

### Run from source

Due to the dependence on system libraries and GTK ecosystem, Social Coding Report requires a build step and cannot be run directly from source.
However, you can still try running it in development by:

```console
$ meson setup __build --prefix ~/.local/
$ ninja -C __build
$ ninja -C __build install
$ socialcodingreport
```

These steps will install Social Coding Report to *~/.local/*. Everytime we modify source code, we only need to run the ``meson install ...`` step again.

To enable debug log, do:

```console
$ G_MESSAGES_DEBUG=socialcodingreport socialcodingreport
```

To uninstall, do:

```console
$ ninja -C __build uninstall
```

## Configuration

Repositories can be managed directly via the Preferences window in the application.
Configuration is stored in `~/.config/socialcodingreport/config.toml`.

## License

This project is licensed under the terms of the GNU General Public License v3.0 (GPL-3.0). See the [LICENSE](LICENSE) file for details.
Icon from vecteezy.com.
