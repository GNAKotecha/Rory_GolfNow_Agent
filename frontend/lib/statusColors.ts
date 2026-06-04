export const getStatusColors = (
  status: string
): { textColor: string; bgColor: string } => {
  switch (status) {
    case 'healthy':
      return {
        textColor: 'text-green-600',
        bgColor: 'bg-green-50 border-green-200',
      };
    case 'unhealthy':
      return {
        textColor: 'text-red-600',
        bgColor: 'bg-red-50 border-red-200',
      };
    default:
      return {
        textColor: 'text-gray-600',
        bgColor: 'bg-gray-50 border-gray-200',
      };
  }
};
