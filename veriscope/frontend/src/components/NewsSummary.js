import React from 'react';
import BiasIndicator from './BiasIndicator';

const NewsSummary = ({ article }) => {
  return (
    <div className="bg-gray-800 p-4 rounded-lg">
      <h2 className="text-xl font-semibold mb-2">{article.title}</h2>
      <p className="text-gray-300 mb-4">{article.summary}</p>
      <div className="flex justify-between items-center">
        <span className="text-sm text-gray-400">{article.source}</span>
        <BiasIndicator bias={article.bias} />
      </div>
    </div>
  );
};

export default NewsSummary;
