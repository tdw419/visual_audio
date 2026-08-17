fn main() {
    for num_nodes in 3..=5 {
        println!("--- Layout for {} nodes ---", num_nodes);
        let columns = (num_nodes as f32).sqrt().ceil() as usize;
        let spacing_x = 1.4;
        let spacing_y = 1.4;
        let start_x = -((columns as f32 - 1.0) * spacing_x) * 0.5;
        let start_y = (((num_nodes as f32) / columns as f32).ceil() - 1.0) * spacing_y * 0.5;

        for i in 0..num_nodes {
            let col = i % columns;
            let row = i / columns;
            let target_x = start_x + col as f32 * spacing_x;
            let target_y = start_y - row as f32 * spacing_y;
            println!("Node {}: target ({:.2}, {:.2})", i, target_x, target_y);
        }
    }
}
