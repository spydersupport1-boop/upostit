/// Lifecycle status of an employee device binding.
enum DeviceBindingStatus {
  active,
  pendingApproval,
  revoked,
  replaced,
  unregistered;

  static DeviceBindingStatus fromString(String? value) {
    if (value == null) return DeviceBindingStatus.unregistered;
    switch (value.toUpperCase()) {
      case 'ACTIVE':
        return DeviceBindingStatus.active;
      case 'PENDING_APPROVAL':
        return DeviceBindingStatus.pendingApproval;
      case 'REVOKED':
        return DeviceBindingStatus.revoked;
      case 'REPLACED':
        return DeviceBindingStatus.replaced;
      default:
        return DeviceBindingStatus.unregistered;
    }
  }

  String toDisplayString() {
    switch (this) {
      case DeviceBindingStatus.active:
        return 'Active';
      case DeviceBindingStatus.pendingApproval:
        return 'Pending Approval';
      case DeviceBindingStatus.revoked:
        return 'Revoked';
      case DeviceBindingStatus.replaced:
        return 'Replaced';
      case DeviceBindingStatus.unregistered:
        return 'Unregistered';
    }
  }

  bool get canPunch => this == DeviceBindingStatus.active;
}
