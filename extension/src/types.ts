export interface LocationInfo {
  start_line?: number | null;
  start_col?: number | null;
  end_line?: number | null;
  end_col?: number | null;
}

export interface BaseNodeData {
  name?: string;
  qualname?: string;
  path?: string | null;
  type?: string; 
  loc?: LocationInfo;
  [key: string]: any;
}

export interface GraphNode {
  id: string;
  data: BaseNodeData;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
