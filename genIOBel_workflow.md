```mermaid
graph TD
    A[Start genIOBel] --> B{gen_ios list empty?};
    B -- Yes --> C[Log message & Return None];
    B -- No --> D{BEL file exists AND<br>overwrite is False?};
    D -- Yes --> E[Parse existing BEL file];
    E --> F[Return existing Bel object];
    
    D -- No --> G[Initialize HDL Writer<br>(Verilog or VHDL)];
    G --> H[Calculate total ConfigBits from all gen_ios];
    H --> I[Process gen_ios list:<br>Determine internal/external ports,<br>clock requirements, etc.];
    I --> J[Generate HDL Code in Memory];
    subgraph J [Generate HDL Code in Memory]
        direction LR
        J1[Module/Entity Header & Ports] --> J2{Any config access IOs?};
        J2 -- Yes --> J3[Generate ConfigBit assignments];
        J2 -- No --> J4;
        J3 --> J4;
        J4[Generate I/O Logic:<br>- Combinatorial assignments<br>- Registers for clocked IOs<br>- Multiplexers if needed];
        J4 --> J5[Module/Entity End];
    end
    
    J --> K[Write generated code to BEL file];
    K --> L[Parse the new BEL file to create a Bel object];
    L --> M[Add Bel to synthesis primitives file<br>(custom_prims.v via addBelsToPrim)];
    M --> N[Return new Bel object];

    style C fill:#f9f,stroke:#333,stroke-width:2px
    style F fill:#f9f,stroke:#333,stroke-width:2px
    style N fill:#f9f,stroke:#333,stroke-width:2px
```
