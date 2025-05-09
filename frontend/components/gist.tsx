"use client";
import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
// ReactionButtons import removed as it seems unused directly here, but keep if needed elsewhere
import { Synthesis } from "@/components/synthesis";

import { motion, useAnimation } from "framer-motion";
import { Button } from "@/components/ui/button";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import {
  naiveRecAlgo,
  likeCluster,
  dislikeCluster,
  // viewCluster, // Uncomment if used
  // readCluster, // Uncomment if used
  getClusterById,
  getArticlesByClusterId
} from "@/lib/actions/clusters";
import { Sources } from "./sources";

// Define an interface for your cluster data for better type safety
interface Cluster {
  id: string;
  title?: string; // Mark optional if they can be null/undefined
  summary?: string;
  key_takeaways?: string[];
  created_at?: string; // Or Date
  synthesis?: string;
  // Add other properties from your Supabase cluster table
  [key: string]: any; // Allow other properties if needed
}

interface Article {
    id: string;
    title?: string;
    publisher?: string;
    url?: string;
    top_image?: string | null;
    // Add other article properties
    [key: string]: any;
}


export function Gist({ currentClusterID }: { currentClusterID: string }) {
  // Initialize state with null or specific types
  const [currentCluster, setCurrentCluster] = useState<Cluster | null>(null); // Use null initially
  const [nextClusters, setNextClusters] = useState<Cluster[]>([]); // Expect an array of Clusters
  const [isLoading, setIsLoading] = useState(true); // Keep track of loading state
  const [articles, setArticles] = useState<Article[]>([]); // Expect an array of Articles
  const [imageArticle, setImageArticle] = useState<Article | null>(null); // Store the article with the image

  const controls = useAnimation();
  // const [direction, setDirection] = useState(0); // direction state seems unused

  // Fetch current cluster data
  useEffect(() => {
    if (!currentClusterID) return; // Don't fetch if ID is invalid

    const fetchCluster = async () => {
      setIsLoading(true); // Set loading true when starting fetch
      console.log(`Gist: Fetching cluster ${currentClusterID}`);
      try {
        const cluster = await getClusterById(currentClusterID); // Returns Cluster or null
        setCurrentCluster(cluster); // Set state (can be null)
        if (!cluster) {
            console.error(`Gist: Cluster ${currentClusterID} not found.`);
            // Handle not found case - maybe show an error message or redirect?
        }
      } catch (error) {
        console.error("Gist: Error fetching cluster:", error);
        setCurrentCluster(null); // Set to null on error
      } finally {
        // setIsLoading(false); // Loading finished (moved to fetchArticles effect)
      }
    };

    fetchCluster();
  }, [currentClusterID]); // Add dependency array

  // Fetch next clusters (recommendations) - runs once on mount
  useEffect(() => {
    const fetchNextClusters = async () => {
      console.log("Gist: Fetching next clusters...");
      try {
        const clusters = await naiveRecAlgo([], 5); // Fetch recommendations
        setNextClusters(clusters || []); // Ensure it's an array
      } catch (error) {
        console.error("Gist: Error fetching next clusters:", error);
        setNextClusters([]); // Set empty on error
      }
    };

    fetchNextClusters();
  }, []); // Empty dependency array means run once

  // Fetch articles for the current cluster when it changes or ID changes
  useEffect(() => {
    if (!currentClusterID) {
        setArticles([]); // Clear articles if no ID
        setImageArticle(null);
        setIsLoading(false); // Stop loading if no ID
        return;
    };

    const fetchArticles = async () => {
      console.log(`Gist: Fetching articles for cluster ${currentClusterID}`);
      try {
        let fetchedArticles: Article[] = await getArticlesByClusterId(currentClusterID);
        // Filter out duplicates based on title and publisher
        fetchedArticles = fetchedArticles.filter((article, index, self) =>
          article && article.title && article.publisher && // Ensure properties exist before comparing
          index === self.findIndex((t) => (
            t && t.title === article.title && t.publisher === article.publisher
          ))
        );
        setArticles(fetchedArticles);
        // Find an article with a top_image
        const articleWithImage = fetchedArticles.find(article => article && article.top_image);
        setImageArticle(articleWithImage || null);
      } catch (error) {
        console.error("Gist: Error fetching articles:", error);
        setArticles([]); // Clear articles on error
        setImageArticle(null);
      } finally {
         setIsLoading(false); // Set loading false after articles are fetched (or fail)
      }
    }
    fetchArticles();
  }, [currentClusterID]); // Depend on currentClusterID

  // Logging effects (optional for debugging)
  useEffect(() => {
    console.log("Gist: currentCluster state updated", currentCluster);
  }, [currentCluster]);

  useEffect(() => {
    console.log("Gist: nextClusters state updated", nextClusters);
  }, [nextClusters]);

   useEffect(() => {
     console.log("Gist: articles state updated", articles);
   }, [articles]);

   useEffect(() => {
     console.log("Gist: imageArticle state updated", imageArticle);
   }, [imageArticle]);


  // Function to advance to the next cluster from the recommendations
  function nextGist() {
    setNextClusters((prevNextClusters) => {
      if (prevNextClusters.length > 0) {
        const firstCluster = prevNextClusters[0];
        const updatedNextClusters = [...prevNextClusters.slice(1)]; // Don't cycle back immediately, fetch more later if needed

        // Update the current cluster ID in the URL, which triggers data fetching via useEffect
        // This requires access to the router
        // router.push(`/news/${firstCluster.id}`); // <-- Needs router instance

        // For now, just update state directly (less ideal than route change)
        setCurrentCluster(firstCluster);
        // Fetch new recommendations if the queue gets low? (More advanced logic)
        if (updatedNextClusters.length < 3) { // Example threshold
            console.log("Gist: Fetching more recommendations...");
            naiveRecAlgo([], 5).then(newClusters => {
                setNextClusters(prev => [...prev, ...(newClusters || [])]);
            }).catch(err => console.error("Failed to fetch more clusters:", err));
        }

        return updatedNextClusters;
      } else {
        console.log("Gist: No more clusters in queue. Fetching new ones.");
        // Fetch new clusters if the queue is empty
         naiveRecAlgo([], 5).then(newClusters => {
             if (newClusters && newClusters.length > 0) {
                 setCurrentCluster(newClusters[0]);
                 setNextClusters(newClusters.slice(1));
             } else {
                 // Handle case where no clusters can be fetched
                 console.error("Gist: Could not fetch any new clusters.");
                 // Maybe show a message to the user
             }
         }).catch(err => console.error("Failed to fetch initial clusters after empty queue:", err));
        return []; // Return empty while fetching
      }
    });
  }


  // Keydown handler for liking/disliking
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!currentCluster?.id) return; // Don't do anything if no current cluster

      if (event.metaKey || event.ctrlKey) { // Allow Ctrl+J/K too
        if (event.key === "j") {
          event.preventDefault(); // Prevent browser find action
          // Slide left for Like (J)
          // setDirection(-1); // Seems unused
          controls.start({ x: "-100vw", opacity: 0 }).then(() => {
            likeCluster(currentCluster.id).catch(err => console.error("Failed to like cluster:", err));
            nextGist(); // Load next cluster data
            controls.set({ x: "100vw" }); // Reset position off-screen right
            controls.start({ x: 0, opacity: 1 }); // Animate in
          });
        } else if (event.key === "k") {
          event.preventDefault();
          // Slide right for Dislike (K)
          // setDirection(1); // Seems unused
          controls.start({ x: "100vw", opacity: 0 }).then(() => {
            dislikeCluster(currentCluster.id).catch(err => console.error("Failed to dislike cluster:", err));
            nextGist(); // Load next cluster data
            controls.set({ x: "-100vw" }); // Reset position off-screen left
            controls.start({ x: 0, opacity: 1 }); // Animate in
          });
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    // Cleanup function
    return () => window.removeEventListener("keydown", handleKeyDown);
    // Add currentCluster.id to dependencies so the correct ID is used in like/dislike
  }, [controls, currentCluster?.id, nextGist]); // Added currentCluster.id and nextGist

  // --- Loading State ---
  if (isLoading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          height: "80vh",
        }}
      >
        <img
          src="/synthesis.png"
          alt="Loading..."
          className="animate-spin"
          style={{ height: "8vh", marginBottom: "2vh" }}
        />
        <p>Loading the gists...</p>
      </div>
    );
  }

  // --- Error State ---
  if (!currentCluster) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          height: "80vh",
        }}
      >
        <p>Cluster not found or could not be loaded. Please try another.</p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => nextGist()}
        >
          Try Another Cluster
        </Button>
      </div>
    );
  }

  // --- Render Component ---
  // Now we know currentCluster is a valid object (or was intended to be)
  return (
    <>
      <motion.div
        initial={{ x: 0, opacity: 1 }}
        animate={controls}
        transition={{ type: "tween" }}
        className="container relative max-w-3xl py-6 lg:py-10"
      >
        <div className={`card-animation-container`}>
          {/* Use optional chaining (?.) for safety when accessing properties */}
          <Card className="max-w-2xl overflow-hidden m-4">
            <CardHeader className="flex flex-col gap-1 m-0 pb-4 bg-background">
              <CardTitle className="text-3xl font-bold">
                {currentCluster.title ?? "Untitled Cluster"} {/* Use nullish coalescing */}
              </CardTitle>
              <div className="flex flex-row space-between items-end">
                <CardDescription className="leading-relaxed">
                  {currentCluster.summary ?? "No summary available."} {/* Use nullish coalescing */}
                </CardDescription>
                {/* Like/Dislike buttons - consider making them functional */}
                <div className="flex flex-row space-x-2 ml-auto">
                   <Button variant="outline" size="sm" className="px-1" onClick={() => { /* Add like logic */ }}>
                     <ThumbsUp className="h-4 w-4 mr-2" />
                     <p className="text-sm text-muted-foreground">
                       <span className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
                         <span className="text-xs">⌘</span>J
                       </span>
                     </p>
                   </Button>
                   <Button variant="outline" size="sm" className="px-1" onClick={() => { /* Add dislike logic */ }}>
                     <ThumbsDown className="h-4 w-4 mr-2" />
                     <p className="text-sm text-muted-foreground">
                       <span className="pointer-events-none inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
                         <span className="text-xs">⌘</span>K
                       </span>
                     </p>
                   </Button>
                 </div>
              </div>
            </CardHeader>
            <Separator className="mb-4" />
            <CardContent className="flex flex-col space-y-6">
              <div>
                <h2 className="font-semibold text-xl mb-4 mt-2">Takeaways</h2>
                {/* Check if key_takeaways exists and is an array */}
                {Array.isArray(currentCluster.key_takeaways) && currentCluster.key_takeaways.length > 0 ? (
                  <ul className="list-disc ml-8 text-sm space-y-2">
                    {currentCluster.key_takeaways.map((takeaway, i) => (
                      <li key={i}>{takeaway}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">No takeaways available.</p>
                )}
              </div>
            </CardContent>
            <CardFooter className="pb-0 px-0 -mx-2">
              {/* Footer content if any */}
            </CardFooter>
          </Card>
        </div>
      </motion.div>

      {/* Pass potentially null/undefined props safely to Synthesis */}
      <Synthesis
        title={currentCluster.title ?? "Untitled"}
        synthesized_at={currentCluster.created_at ?? new Date().toISOString()} // Provide a default date
        synthesis={currentCluster.synthesis ?? "No synthesis available."}
      />
      {/* Pass articles array to Sources */}
      <Sources
        articles={articles}
      />
    </>
  );
}