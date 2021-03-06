
class DevMan(object):
    """Device Manager class. Maintains the loaded model list, groups and categories"""
    def __init__(self, system=None):
        """constructor for DevMan class"""
        self.system = system
        self.devices = []
        self.group = {}

    def register_device(self, dev_name):
        """register a device to the device list"""
        if dev_name not in self.devices:
            self.devices.append(dev_name)
        group_name = self.system.__dict__[dev_name]._group
        if group_name not in self.group.keys():
            self.group[group_name] = {}

    def register_element(self, dev_name, idx=None):
        """register a device element to the group list
        Args:
            dev_name: model name
            idx (optional): element external idx

        Returns:
            idx: assigned element index
            """
        if dev_name not in self.devices:
            self.system.Log.error('Device {} missing. Call add_device before adding elements'.format(dev_name))
            return
        group_name = self.system.__dict__[dev_name]._group
        if idx is None:  # "if not idx" will fail for idx==0.0
            idx = len(self.group[group_name].keys())
        self.group[group_name][idx] = dev_name
        return idx

    def sort_device(self):
        """sort device to meet device prerequisites (initialize devices before controllers)"""
        self.devices.sort()
        if 'Bus' in self.devices:
            k = self.devices.index('Bus')
            self.devices[k] = self.devices[0]
            self.devices[0] = 'Bus'
        if 'Node' in self.devices:
            k = self.devices.index('Node')
            self.devices[k] = self.devices[1]
            self.devices[1] = 'Node'
        if 'Ground' in self.devices:
            k = self.devices.index('Ground')
            self.devices[k] = self.devices[2]
            self.devices[2] = 'Ground'

