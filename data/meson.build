install_data(
  'report.html.jinja',
  install_dir: get_option('datadir') / meson.project_name() / 'data'
)

install_data(
  'vn.ququ.SocialCodingReport.desktop',
  install_dir: get_option('datadir') / 'applications'
)

# Install SVG icons to proper XDG icon directory
install_data(
  'vn.ququ.SocialCodingReport.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps'
)

# Use GNOME post-install hooks
gnome = import('gnome')
gnome.post_install(
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
