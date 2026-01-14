pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'socialcodingreport'

gnome = import('gnome')

# Blueprints
blueprints = custom_target('blueprints',
  input: files(
    'ui/window.blp',
    'ui/report_page.blp',
    'ui/preferences_page.blp',
  ),
  output: 'gtk',
  command: ['blueprint-compiler', 'batch-compile', '@OUTPUT@', '@CURRENT_SOURCE_DIR@/ui', '@INPUT@'],
)

# Resources
resources = gnome.compile_resources(
  'socialcodingreport',
  'socialcodingreport.gresource.xml',
  dependencies: blueprints,
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
)

# Python Sources
python_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'models.py',
  'config.py',
  'github_client.py',
  'consts.py',
  'app_logging.py',
]

install_data(python_sources, install_dir: moduledir)

subdir('pages')

# Launcher
python = import('python')
conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3').full_path())
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'socialcodingreport.in',
  output: 'socialcodingreport',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

