// frontend/app/news/page.tsx
import { redirect } from 'next/navigation';
import { cookies } from 'next/headers';
import { createClient } from '@/utils/supabase/server';
import { naiveRecAlgo } from '@/lib/actions/clusters'; // Assuming this can be called server-side now

// This page becomes a Server Component to fetch the initial cluster
export default async function NewsRedirectPage() {
  // Note: naiveRecAlgo uses cookies(), so this component becomes dynamic,
  // or you modify naiveRecAlgo to accept a Supabase client instance.
  // Let's assume naiveRecAlgo works server-side for now.

  console.log("NewsRedirectPage: Fetching initial cluster...");
  let firstClusterId: string | null = null;

  try {
    // Fetch just one recommended cluster to get an ID
    const recommendedClusters = await naiveRecAlgo([], 1);

    if (recommendedClusters && recommendedClusters.length > 0 && recommendedClusters[0]?.id) {
      firstClusterId = recommendedClusters[0].id;
      console.log(`NewsRedirectPage: Found first cluster ID: ${firstClusterId}`);
    } else {
      console.log("NewsRedirectPage: No recommended clusters found.");
      // Handle case where no clusters exist yet
      // Option 1: Redirect home
      // redirect('/');
      // Option 2: Show a message (would require changing this to return JSX)
      return (
          <div className="flex justify-center items-center h-screen">
              <p>No news available yet. Please check back later.</p>
          </div>
      );
    }
  } catch (error) {
    console.error("NewsRedirectPage: Error fetching initial cluster:", error);
     // Option 1: Redirect home on error
     // redirect('/');
     // Option 2: Show error message
     return (
        <div className="flex justify-center items-center h-screen">
            <p>Error loading news. Please try again later.</p>
        </div>
     );
  }

  // If we found an ID, redirect to it
  if (firstClusterId) {
    redirect(`/news/${firstClusterId}`);
  }

  // Fallback if redirect didn't happen (e.g., error handled by returning JSX)
  return null;
}