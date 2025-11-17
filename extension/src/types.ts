export interface GraphNode {
  id: string;
  // любое содержимое, которое положил бэк (module, class, etc)
  data: any;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
