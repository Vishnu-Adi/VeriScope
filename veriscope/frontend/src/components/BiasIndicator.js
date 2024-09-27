import React from 'react';

const BiasIndicator = ({ bias }) => {
  const getColor = () => {
    if (bias < -0.5) return 'bg-red-500';
    if (bias < 0) return 'bg-yellow-500';
    if (bias < 0.5) return 'bg-green-500';
    return 'bg-blue-500';
  };

  return (
    <div className="flex items-center">
      <div className={`w-4 h-4 rounded-full ${getColor()} mr-2`}></div>
      <span className="text-sm">Bias: {bias.toFixed(2)}</span>
    </div>
  );
};

export default BiasIndicator;