from typing import Any

import gi


gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GObject, Gio, GLib, Gtk
from logbook import Logger

from ..config import ConfigManager
from ..consts import Host
from ..models import Account, AccountItem, RepoInfo, RepoItem


log = Logger(__name__)


@Gtk.Template.from_resource('/vn/ququ/SocialCodingReport/gtk/preferences_page.ui')
class PreferencesPage(Adw.Bin):
    __gtype_name__ = 'PreferencesPage'

    repos_group: Adw.PreferencesGroup = Gtk.Template.Child()
    entry_add_repo: Adw.EntryRow = Gtk.Template.Child()
    repos_list_box: Gtk.ListBox = Gtk.Template.Child()
    entry_add_account: Adw.EntryRow = Gtk.Template.Child()
    entry_github_token: Adw.PasswordEntryRow = Gtk.Template.Child()
    accounts_list_box: Gtk.ListBox = Gtk.Template.Child()

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)

        self.config = ConfigManager()

        self.repo_store = Gio.ListStore(item_type=RepoItem)
        self.account_store = Gio.ListStore(item_type=AccountItem)

        # Setup actions
        action_group = Gio.SimpleActionGroup()
        self.insert_action_group('preferences', action_group)

        action_remove = Gio.SimpleAction.new('remove-repo', GLib.VariantType.new('s'))
        action_remove.connect('activate', self.on_remove_repo)
        action_group.add_action(action_remove)

        action_remove_account = Gio.SimpleAction.new('remove-account', GLib.VariantType.new('s'))
        action_remove_account.connect('activate', self.on_remove_account)
        action_group.add_action(action_remove_account)

        # Bind model
        self.repos_list_box.bind_model(self.repo_store, self.create_repo_row)
        self.accounts_list_box.bind_model(self.account_store, self.create_account_row)

        self.load_repos()
        self.load_accounts()

    def create_repo_row(self, item: RepoItem) -> Gtk.Widget:
        row = Adw.ActionRow(title=item.display_name, activatable=False)

        btn = Gtk.Button(icon_name='user-trash-symbolic')
        btn.add_css_class('flat')
        btn.set_valign(Gtk.Align.CENTER)

        # Action target must be GLib.Variant
        btn.set_action_name('preferences.remove-repo')
        btn.set_action_target_value(GLib.Variant.new_string(item.display_name))

        row.add_suffix(btn)
        return row

    def create_account_row(self, item: AccountItem) -> Gtk.Widget:
        row = Adw.ActionRow(activatable=True)
        item.bind_property('username', row, 'title', GObject.BindingFlags.SYNC_CREATE)
        row.set_subtitle('Click to edit')

        edit_icon = Gtk.Image(icon_name='document-edit-symbolic')
        edit_icon.set_valign(Gtk.Align.CENTER)
        row.add_suffix(edit_icon)

        btn = Gtk.Button(icon_name='user-trash-symbolic')
        btn.add_css_class('flat')
        btn.set_valign(Gtk.Align.CENTER)

        btn.set_action_name('preferences.remove-account')
        btn.set_action_target_value(GLib.Variant.new_string(item.host))

        row.add_suffix(btn)
        return row

    def load_repos(self):
        self.repo_store.remove_all()
        repos = self.config.load_repositories()
        for repo in repos:
            self.repo_store.append(RepoItem(owner=repo.owner, name=repo.name, host=repo.host))

    def load_accounts(self):
        self.account_store.remove_all()
        accounts = self.config.load_accounts()
        for account in accounts:
            self.account_store.append(AccountItem(username=account.username, host=account.host, token=account.token))

    @Gtk.Template.Callback()
    def on_add_repo(self, entry: Adw.EntryRow):
        text = entry.get_text().strip()
        if text:
            # Check for duplicate
            for i in range(self.repo_store.get_n_items()):
                item = self.repo_store.get_item(i)
                if item.display_name == text:
                    return

            # Check format "owner/name"
            if '/' not in text:
                return

            owner, name = text.split('/', 1)

            # Update Config
            # We need to construct RepoInfo. Assuming GitHub for now as per plan
            new_repo = RepoInfo(owner=owner, name=name, host=Host.GITHUB)

            repos = list(self.config.load_repositories())
            # Simple check for existence
            if new_repo not in repos:
                repos.append(new_repo)
                self.config.save_repositories(repos)

                # Update UI
                self.repo_store.append(RepoItem(owner=owner, name=name, host=Host.GITHUB))

            entry.set_text('')

    @Gtk.Template.Callback()
    def on_add_account(self, btn: Gtk.Button):
        username = self.entry_add_account.get_text().strip()
        token = self.entry_github_token.get_text().strip() or None
        host = Host.GITHUB  # Assuming GitHub for these fields for now

        if not username:
            return

        # Load current accounts
        accounts = list(self.config.load_accounts())
        existing_account = next((a for a in accounts if a.host == host), None)

        if existing_account:
            # Update existing
            existing_account.username = username
            existing_account.token = token
            log.info('Updated account for {}: {}', host, username)
        else:
            # Add new
            new_account = Account(username=username, host=host, token=token)
            accounts.append(new_account)
            log.info('Added account for {}: {}', host, username)

        self.config.save_accounts(accounts)

        # Update UI store
        found_in_store = False
        for i in range(self.account_store.get_n_items()):
            item = self.account_store.get_item(i)
            if item.host == host:
                item.username = username
                item.token = token or ''
                found_in_store = True
                break

        if not found_in_store:
            self.account_store.append(AccountItem(username=username, host=host, token=token))

        self.entry_add_account.set_text('')
        self.entry_github_token.set_text('')

    @Gtk.Template.Callback()
    def on_account_activated(self, list_box: Gtk.ListBox, row: Adw.ActionRow):
        # We need to get the item from the row.
        # Adw.ActionRow doesn't store the item directly unless we set it or use indexes.
        # But we can find the index and get from store.
        index = row.get_index()
        item = self.account_store.get_item(index)
        if item:
            self.entry_add_account.set_text(item.username)
            self.entry_github_token.set_text(item.token)
            # Set focus to the token entry to encourage update if needed
            self.entry_github_token.grab_focus()
            log.info('Selected account for editing: {}', item.username)

    def on_remove_repo(self, action, parameter):
        repo_display_name = parameter.get_string()
        if '/' not in repo_display_name:
            return

        owner, name = repo_display_name.split('/', 1)

        # Remove from store
        for i in range(self.repo_store.get_n_items()):
            item = self.repo_store.get_item(i)
            if item.owner == owner and item.name == name:
                self.repo_store.remove(i)
                break

        # Remove from config
        repos = list(self.config.load_repositories())
        repos = [r for r in repos if not (r.owner == owner and r.name == name)]
        self.config.save_repositories(repos)

    def on_remove_account(self, action, parameter):
        host = parameter.get_string()

        # Remove from store
        for i in range(self.account_store.get_n_items()):
            item = self.account_store.get_item(i)
            if item.host == host:
                self.account_store.remove(i)
                break

        # Remove from config
        accounts = list(self.config.load_accounts())
        accounts = [a for a in accounts if a.host != host]
        self.config.save_accounts(accounts)
