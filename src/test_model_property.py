from gi.repository import GLib, GObject


# Mock RepoItem to isolate from app
class RepoItem(GObject.Object):
    __gtype_name__ = 'RepoItem'

    name = GObject.Property(type=str)

    @GObject.Property(type=GObject.TYPE_VARIANT)
    def name_variant(self):
        v = GLib.Variant('s', self.name) if self.name else None
        print(f'DEBUG: name_variant called, name={self.name}, ret={v}')
        return v

    def __init__(self, name: str):
        super().__init__()
        self.name = name


def test():
    item = RepoItem(name='test/repo')
    print(f'Item name: {item.name}')

    # Access property via GObject logic
    full_v = item.get_property('name_variant')
    print(f'Property name_variant direct get: {full_v}')

    if full_v is None:
        print('FAIL: Property returned None')
    elif not isinstance(full_v, GLib.Variant):
        print(f'FAIL: Property returned {type(full_v)} instead of GLib.Variant')
    else:
        print(f'Variant type string: {full_v.get_type_string()}')
        print(f'Variant value: {full_v.get_string()}')
        if full_v.get_type_string() == 's' and full_v.get_string() == 'test/repo':
            print('SUCCESS')
        else:
            print('FAIL: Value mismatch')


if __name__ == '__main__':
    test()
