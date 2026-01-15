from typing import Any

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gio, GLib, Gtk

from ..config import ConfigManager
from ..models import RepoItem


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/preferences_page.ui')
class PreferencesPage(Adw.Bin):
    __gtype_name__ = 'PreferencesPage'

    repos_group: Adw.PreferencesGroup = Gtk.Template.Child()
    entry_add_repo: Adw.EntryRow = Gtk.Template.Child()
    repos_list_box: Gtk.ListBox = Gtk.Template.Child()

    repo_store: Gio.ListStore = Gtk.Template.Child()

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.config = ConfigManager()

        # Setup actions
        action_group = Gio.SimpleActionGroup()
        self.insert_action_group('preferences', action_group)

        action_remove = Gio.SimpleAction.new('remove-repo', GLib.VariantType.new('s'))
        action_remove.connect('activate', self.on_remove_repo)
        action_group.add_action(action_remove)

        # Bind model
        self.repos_list_box.bind_model(self.repo_store, self.create_repo_row)

        self.load_repos()

    def create_repo_row(self, item: RepoItem) -> Gtk.Widget:
        row = Adw.ActionRow(title=item.name, activatable=False)

        btn = Gtk.Button(icon_name='user-trash-symbolic')
        btn.add_css_class('flat')
        btn.set_valign(Gtk.Align.CENTER)

        # Action target must be GLib.Variant
        btn.set_action_name('preferences.remove-repo')
        btn.set_action_target_value(GLib.Variant.new_string(item.name))

        row.add_suffix(btn)
        return row

    def load_repos(self):
        self.repo_store.remove_all()
        repos = self.config.load_repositories()
        for repo_name in repos:
            self.repo_store.append(RepoItem(name=repo_name))

    @Gtk.Template.Callback()
    def on_add_repo(self, entry: Adw.EntryRow):
        text = entry.get_text().strip()
        if text:
            # Check for duplicate
            for i in range(self.repo_store.get_n_items()):
                item = self.repo_store.get_item(i)
                if item.name == text:
                    return

            # Update Config
            repos = list(self.config.load_repositories())
            if text not in repos:
                repos.append(text)
                self.config.save_repositories(repos)

            # Update UI
            self.repo_store.append(RepoItem(name=text))
            entry.set_text('')

    def on_remove_repo(self, action, parameter):
        repo_name = parameter.get_string()

        # Remove from store
        for i in range(self.repo_store.get_n_items()):
            item = self.repo_store.get_item(i)
            if item.name == repo_name:
                self.repo_store.remove(i)
                break

        # Remove from config
        repos = list(self.config.load_repositories())
        if repo_name in repos:
            repos.remove(repo_name)
            self.config.save_repositories(repos)
