"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createClient } from "@/utils/supabase/server";

// Initialize Supabase client once at the module level
// Note: Using cookies() here makes functions dynamic, which is usually intended for actions.
// If this were a pure utility file, you might pass the client instance or cookieStore around.
const cookieStore = cookies();
const supabase = createClient(cookieStore);

/**
 * Fetches recommended clusters for a user, excluding viewed ones.
 * @param currentClusters - Array of clusters currently displayed (currently unused, but could be for filtering).
 * @param n - Number of recommendations to fetch.
 * @returns Array of cluster objects or empty array on error/no user.
 */
export async function naiveRecAlgo(currentClusters: any[], n: number) {
  // --- REMOVED Hardcoded IDs and early return ---
  // const cluster_ids = ['eed09241-f900-41fa-a5b5-e03ea4260411', '3916e1de-38d4-4155-8a61-056e889b6d6c', '3398dbed-6f0d-46e9-8e81-a6b37b86d810', '59068869-441e-448a-9891-acdb96523ed8', '2cd4539b-5771-47c4-8dfa-bba83b95afb2']
  // const clusters = await Promise.all(cluster_ids.map(id => getClusterById(id)))
  // return clusters; // This prevented the actual logic below from running

  // --- Start of Intended Logic ---
  console.log("Running naiveRecAlgo...");

  // Retrieve the user's id
  const { data: userSession, error: userSessionError } = await supabase.auth.getUser();

  if (userSessionError || !userSession?.user) {
    console.error("User session error or user not found:", userSessionError?.message);
    // Decide behavior: redirect to login or return empty recommendations?
    // For now, return empty array. Consider redirect('/') if login is mandatory.
    return [];
  }
  const userId = userSession.user.id;
  console.log("User ID:", userId);

  // Retrieve the user's profile, specifically the 'views' column
  // Use maybeSingle() to handle cases where the profile might not exist yet
  const { data: userProfile, error: userProfileError } = await supabase
    .from("profiles")
    .select("views")
    .eq("id", userId)
    .maybeSingle(); // Use maybeSingle() instead of single()

  if (userProfileError) {
    // Log the error but don't necessarily stop; maybe the user just hasn't viewed anything.
    console.error("Error fetching user profile:", userProfileError.message);
    // Depending on the error, you might return [] or proceed assuming no views.
    // If it's a connection error, returning [] is safer. If it's just 'no rows', proceed.
    if (userProfileError.code === 'PGRST116') { // Code for 'Searched for one row but found 0'
        console.log("User profile not found or no views recorded yet.");
    } else {
        return []; // Return empty on other errors
    }
  }

  // Safely access views, defaulting to an empty array if null or profile doesn't exist
  const viewedClusters = userProfile?.views || [];
  console.log("Viewed Clusters:", viewedClusters);

  // Ensure viewedClusters is an array of strings/UUIDs suitable for the query
  const viewedClusterIdsString = viewedClusters.length > 0 ? viewedClusters.join(",") : '';

  // Query for clusters not viewed by the user
  // Note: Filtering out currentClusters is removed for simplicity, add back if needed.
  const query = supabase
    .from("clusters")
    .select("*") // Select all columns needed
    .not("id", "in", `(${viewedClusterIdsString})`) // Exclude viewed clusters
    .not("synthesis", "is", null) // Ensure clusters have synthesis
    .limit(n * 5); // Fetch more initially to allow for sorting by article count later

  const { data: clustersData, error: clustersError } = await query;

  if (clustersError) {
    console.error("Error fetching clusters:", clustersError.message);
    return [];
  }

  if (!clustersData || clustersData.length === 0) {
    console.log("No new clusters found matching criteria.");
    return [];
  }

  // Calculate article_count client-side and sort
  const enhancedClustersData = clustersData
    .map((cluster) => ({
      ...cluster,
      // Ensure article_ids exists and is an array before getting length
      article_count: Array.isArray(cluster.article_ids) ? cluster.article_ids.length : 0,
    }))
    .sort((a, b) => b.article_count - a.article_count) // Sort by article_count descending
    .slice(0, n); // Take the top 'n' clusters after sorting

  console.log(`Returning ${enhancedClustersData.length} recommended clusters.`);
  return enhancedClustersData;
}


/**
 * Fetches a single cluster by its ID.
 * Uses maybeSingle() to return null if not found, instead of throwing an error.
 * @param id - The UUID of the cluster.
 * @returns The cluster object or null if not found. Throws on other errors.
 */
export async function getClusterById(id: string) {
  if (!id) {
    console.error("getClusterById called with invalid ID:", id);
    return null; // Return null for invalid IDs
  }
  console.log(`Fetching cluster by ID: ${id}`);
  const { data, error } = await supabase
    .from("clusters")
    .select("*")
    .eq("id", id)
    .maybeSingle(); // Use maybeSingle() to handle 0 rows gracefully

  if (error) {
    // Log the specific error but don't throw for '0 rows' case handled by maybeSingle
    if (error.code !== 'PGRST116') { // PGRST116 = 'Searched for one row but found 0'
        console.error(`Error fetching cluster ${id}:`, error.message);
        throw new Error(error.message); // Throw for actual errors
    } else {
        console.log(`Cluster with ID ${id} not found.`);
    }
  }

  // console.log("Cluster data fetched:", data); // Data will be null if not found
  return data; // Returns the cluster object or null
}

/**
 * Updates an array column (likes, dislikes, views, reads) for the current user's profile.
 * @param columnName - The name of the column to update ('likes', 'dislikes', 'views', 'reads').
 * @param id - The cluster ID to add to the array.
 * @returns An object indicating success or failure, e.g., { likes: true }
 */
async function updateUserArrayColumn(columnName: string, id: string) {
  const { data: userSession, error: userSessionError } = await supabase.auth.getUser();
  if (userSessionError || !userSession?.user) {
    console.error("User not authenticated for updateUserArrayColumn");
    // Return a failure indicator or handle as appropriate
    return { [columnName]: false, error: "User not authenticated" };
  }
  const userId = userSession.user.id;

  // 1. Fetch the current array
  const { data: profileData, error: fetchError } = await supabase
    .from("profiles")
    .select(columnName)
    .eq("id", userId)
    .maybeSingle(); // Use maybeSingle to handle profile not existing

  if (fetchError && fetchError.code !== 'PGRST116') {
    console.error(`Error fetching profile column ${columnName} for user ${userId}:`, fetchError.message);
    throw new Error(fetchError.message);
  }

  const currentArray = profileData?.[columnName] || [];

  // 2. Check if ID already exists
  if (Array.isArray(currentArray) && currentArray.includes(id)) {
    console.log(`ID ${id} already exists in ${columnName} for user ${userId}. No update needed.`);
    return { [columnName]: true }; // Indicate success as it's already there
  }

  // 3. Append the new ID and update
  const updatedArray = [...currentArray, id];
  const { error: updateError } = await supabase
    .from("profiles")
    .update({ [columnName]: updatedArray })
    .eq("id", userId);

  if (updateError) {
    console.error(`Error updating profile column ${columnName} for user ${userId}:`, updateError.message);
    throw new Error(updateError.message);
  }

  console.log(`Successfully added ID ${id} to ${columnName} for user ${userId}.`);
  return { [columnName]: true };
}

/**
 * Fetches a single article by its ID.
 * Uses maybeSingle() for robustness.
 * @param id - The UUID of the article.
 * @returns The article object or null if not found. Throws on other errors.
 */
export async function getArticleById(id: string) {
    if (!id) {
        console.error("getArticleById called with invalid ID:", id);
        return null;
    }
    const { data, error } = await supabase
        .from("articles")
        .select("*")
        .eq("id", id)
        .maybeSingle(); // Use maybeSingle

    if (error && error.code !== 'PGRST116') {
        console.error(`Error fetching article ${id}:`, error.message);
        throw new Error(error.message);
    }
    if (!data) {
        console.log(`Article with ID ${id} not found.`);
    }
    return data; // Returns article or null
}

/**
 * Fetches all articles associated with a given cluster ID.
 * Handles cases where the cluster or some articles might not be found.
 * @param id - The UUID of the cluster.
 * @returns An array of article objects found.
 */
export async function getArticlesByClusterId(id: string) {
  const cluster = await getClusterById(id); // Now returns null if cluster not found
  if (!cluster) {
    console.log(`Cluster ${id} not found when fetching articles.`);
    return []; // Return empty array if cluster doesn't exist
  }

  const article_ids = cluster.article_ids || [];
  if (!Array.isArray(article_ids) || article_ids.length === 0) {
    console.log(`Cluster ${id} has no associated article IDs.`);
    return [];
  }

  // Fetch articles and filter out null results (for articles not found)
  const articlePromises = article_ids.map((articleId: string) => getArticleById(articleId));
  const articles = (await Promise.all(articlePromises)).filter(article => article !== null);

  console.log(`Fetched ${articles.length} articles for cluster ${id}.`);
  return articles;
}

// --- Action Functions ---

export async function likeCluster(id: string) {
  console.log(`Liking cluster: ${id}`);
  return updateUserArrayColumn("likes", id);
}

export async function dislikeCluster(id: string) {
  console.log(`Disliking cluster: ${id}`);
  return updateUserArrayColumn("dislikes", id);
}

export async function viewCluster(id: string) {
  console.log(`Viewing cluster: ${id}`);
  return updateUserArrayColumn("views", id);
}

export async function readCluster(id: string) {
  console.log(`Reading cluster: ${id}`);
  return updateUserArrayColumn("reads", id);
}

// --- Placeholder ---
export async function calculateBiasScores(id: string) {
  // Placeholder implementation
  console.log(`Calculating bias scores for cluster: ${id} (Placeholder)`);
  return { left: 0.5, right: 0.4, neutral: 0.1 };
}