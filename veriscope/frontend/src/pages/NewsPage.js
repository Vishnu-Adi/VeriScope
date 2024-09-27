import React, { useState, useEffect } from 'react';
import Header from '../components/Header';
import Footer from '../components/Footer';
import NewsSummary from '../components/NewsSummary';
import { fetchTopNews } from '../utils/newsScraper';
import { processNewsArticles } from '../utils/nlpProcessor';

const NewsPage = () => {
  const [news, setNews] = useState([]);

  useEffect(() => {
    const getNews = async () => {
      const rawNews = await fetchTopNews();
      const processedNews = await processNewsArticles(rawNews);
      setNews(processedNews);
    };
    getNews();
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <Header />
      <main className="container mx-auto mt-8 p-4">
        <h1 className="text-3xl font-bold mb-6">Top News</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {news.map((article) => (
            <NewsSummary key={article.id} article={article} />
          ))}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default NewsPage;