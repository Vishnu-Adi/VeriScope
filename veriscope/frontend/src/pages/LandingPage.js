import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { Link } from 'react-router-dom';
import GlobalNewsIcon from '../components/GlobalNewsIcon';

const LandingPage = () => {
  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="p-4 flex justify-between items-center">
        <div className="flex items-center space-x-2">
          <GlobalNewsIcon className="w-8 h-8 text-blue-500" />
          <h1 className="text-xl font-bold">VeriScope</h1>
        </div>
        <div className="flex items-center space-x-4">
          <input
            type="text"
            placeholder="Search..."
            className="px-3 py-1 bg-gray-800 rounded-full text-sm"
          />
          <button className="p-1 rounded-full hover:bg-gray-800">
            <Moon size={20} />
          </button>
          <button className="px-4 py-1 bg-blue-500 rounded-full text-sm">
            Login
          </button>
        </div>
      </header>
      <main className="container mx-auto mt-16 text-center">
        <h1 className="text-5xl font-bold mb-4">VeriScope</h1>
        <p className="text-xl mb-8">The Truly-Unbiased News Platform.</p>
        <div className="w-64 h-64 mx-auto mb-8">
          <GlobalNewsIcon className="w-full h-full text-blue-500" />
        </div>
        <Link to="/news" className="px-6 py-3 bg-blue-500 rounded-full text-lg font-semibold inline-block">
          Jump into VeriScope
        </Link>
        <p className="mt-4 text-gray-400">Enjoy your news on your own terms.</p>
      </main>
    </div>
  );
};

export default LandingPage;