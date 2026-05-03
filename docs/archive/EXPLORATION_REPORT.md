# MineGPT - Reporte de Exploracion del Wiki

| Archivo | Registros | Palabras |
|---------|-----------|----------|
| articles.jsonl | 13897 | 12,387,230 |
| changelogs.jsonl | 1271 | 2,192,331 |

---
## 1. Distribucion de longitud

| Rango | Cantidad |
|-------|----------|
| 0 vacios | 14 |
| 1-9 | 92 |
| 10-49 | 3131 |
| 50-99 | 1357 |
| 100-499 | 4853 |
| 500-999 | 1887 |
| 1000-4999 | 2261 |
| 5000-9999 | 215 |
| 10000+ | 87 |

---
## 2. DEBUG MODE (10 articles, 2.26M palabras) - Propuesta: GUARDAR APARTE

Son listas gigantes de block IDs. Ejemplo:

#### Debug mode (1555 words)
```
This article is about the world type . For other uses, see Debug .
This feature is exclusive to Java Edition .
The world generation in debug mode
Debug mode usually refers to a world preset used to test block states , block models , and textures .
Debug mode can also refer to a dimension generator type ( minecraft:debug ) that generates a block grid, which is used in the "Debug mode" w
Debug mode can also refer to a state of a world, if the Overworld uses the "debug" generator, the world goes into the debug mode state. In t
Debug mode world preset
Debug mode selected; note that all of the other world settings are unavailable.
To select the debug mode, hold the Alt key while clicking the "World Type" button in the world creation menu. Debug mode is the world type d
Upon selecting debug mode, the "Bonus Chest", "Generate Structures", "Allow Cheats" and "Data Packs" options are forcibly disabled. The game
Debug generator
The minecraft:debug generator contains all blocks , in all of their existing block states , organized in a single world. The world updates a
Block grid
The entire grid as seen from above. East is up.
Every block state generates only once or, in a few cases in some versions, twice. They are sorted in a grid spread across an altitude of Y=7
... (86 lines total)
```

#### Debug mode/Blocks (168716 words)
```
For each row in separate collapsed tables, see Debug mode/Grid .
This article is a dynamic list .
Its subject matter requires frequent updates to remain current and complete, so please help expand and improve it, even if it may never meet
This feature is exclusive to Java Edition .
This is a list of the 29,873 blocks in the debug mode world type. They are listed in the same order as the world type.
Block: Air, ID: air, State: -
Block: Stone, ID: stone, State: -
Block: Granite, ID: granite, State: -
Block: Polished Granite, ID: polished_granite, State: -
Block: Diorite, ID: diorite, State: -
Block: Polished Diorite, ID: polished_diorite, State: -
Block: Andesite, ID: andesite, State: -
Block: Polished Andesite, ID: polished_andesite, State: -
Block: Grass Block, ID: grass_block, State: snowy=true
Block: snowy=false
... (29878 lines total)
```

---
## 3. RENDER/TEXTURE HISTORY (2,711 articles) - Propuesta: ELIMINAR

Metadata de como se veia un bloque en cada version. Mayoria <50 palabras.

#### Java Edition item texture history/White Bundle (25 words)
```
This article is a Java Edition item texture history subpage.
This template is used to categorize the article.
Main article: White Bundle
Java Edition 24w33a
```

#### Bedrock Edition item texture history/Archer Pottery Sherd (31 words)
```
This article is a Bedrock Edition item texture history subpage.
This template is used to categorize the article.
Main article: Archer Pottery Sherd
Bedrock Edition Preview 1.19.70.23
Bedrock Edition Preview 1.19.80.20
```

#### Bedrock Edition block render history/Brown Mushroom Block (33 words)
```
This article is a Bedrock Edition block render history subpage.
This template is used to categorize the article.
Main article: Brown Mushroom Block
Pocket Edition v0.9.0 alpha build 1
Bedrock Edition beta 1.10.0.3
```

#### Java Edition block render history/Bamboo Shoot (25 words)
```
This article is a Java Edition block render history subpage.
This template is used to categorize the article.
Main article: Bamboo Shoot
Java Edition 18w43a
```

#### Bedrock Edition item texture history/Strider Spawn Egg (31 words)
```
This article is a Bedrock Edition item texture history subpage.
This template is used to categorize the article.
Main article: Strider Spawn Egg
Bedrock Edition beta 1.16.0.57
Bedrock Edition Preview 1.21.70.24
```

#### Bedrock Edition item texture history/Rabbit Spawn Egg (33 words)
```
This article is a Bedrock Edition item texture history subpage.
This template is used to categorize the article.
Main article: Rabbit Spawn Egg
Pocket Edition v0.13.0 alpha build 1
Bedrock Edition Preview 1.21.70.24
```

---
## 4. SPIN-OFFS - Propuesta: INCLUIR TODO

### Dungeons (1158 articles)
#### Dungeons:Gloopy Bow (323 words)
```
For other uses, see Bow (disambiguation) .
Type: Ranged Weapon
Rarity: UNIQUE
Power: 3.02
Speed: 3.41
Ammo: 6.57
Properties: Bubble damage Hits multiple targets when charged Special event item
Enchantment: Reliable Ricochet
Damage type: Ranged
Soul information: Does not accept soul enchantments Does not grant soul collection
... (55 lines total)
```

#### Dungeons:Emerald Shield (117 words)
```
For other uses, see Emerald family .
This page describes content that is a part of the Howling Peaks DLC.
Rarity: Common
Applicable to: Armor
In-game description Brief damage immunity when collects an emerald
Emerald Shield is an enchantment that can be found within certain unique armor of Minecraft Dungeons .
Obtaining
Emerald Shield can only be found built-into the following armor:
Opulent Armor
Usage
... (16 lines total)
```

### Legends (340 articles)
#### Legends:Nomad Horse (67 words)
```
For other uses, see Horse (disambiguation) .
Rarity: Regular
Type: Horse
Cost: 160 Minecoins
Obtained from: Marketplace
In-game description This trusty steed is sworn to carry your wares, and it doesn't mind charging into battle on occasion.
Nomad horse is a regular horse skin that can be bought from the Marketplace for 160 Minecoins within Minecraft Legends .
Gallery
As seen in the Marketplace
Details
... (11 lines total)
```

#### Legends:Chainmail Magus (77 words)
```
Rarity: Deluxe
Type: Hero
Cost: 310 Minecoins
Obtained from: Marketplace
Variant of: Magus
In-game description This magus is ready to bring the pain and is equipped to feel none of it! As sturdy as this armor is, we would not recom
Chainmail magus is a deluxe hero skin that can be bought from the Marketplace for 310 Minecoins within Minecraft Legends .
Gallery
As seen in the Marketplace
Details
... (11 lines total)
```

### Earth (136 articles)
#### Earth:Mottled Pig (350 words)
```
For other uses, see Pig (disambiguation) .
Health points: 10 HP
Behavior: Passive
Mob type: Animal
Hitbox size: Height: 0.9 blocks Width: 0.9 blocks
Spawn: Forest
Rarity: Uncommon
Player journal description A pig with stripes. Who knew they had such a sense of style?
The mottled pig was a variant of the pig with gray striped skin found only in Minecraft Earth .
Behavior
... (51 lines total)
```

#### Earth:0.24.0 (169 words)
```
Game: Minecraft Earth
Release date: August 25, 2020
Build version: 2020.0821.05
◄ ◄  0.23.0 Earth:0.24.0 0.25.0 ► ► | ◄ ◄  0.23.0 | Earth:0.24.0 | 0.25.0 ► ►
◄ ◄  0.23.0 | Earth:0.24.0 | 0.25.0 ► ►
0.24.0 is a major update for Minecraft Earth released on August 25, 2020, which adds cookie cows .
Additions
Mobs
Cookie Cow
A variant of the cow .
... (29 lines total)
```

### Story Mode (99 articles)
#### Story Mode:A Portal to Mystery (1365 words)
```
This article is a stub .
You can help by expanding it . The talk page may contain suggestions.
Instructions: Needs images and fill empty sections. Verify the plot details if they are interpreted correctly from the game.
Details
Episode: 6
Season: 1
Release date: June 7, 2016
Written by: Eric Stirpe and Timothy Williams
Directed by: Sean Manning
◄ Order Up! Access Denied ►
... (57 lines total)
```

#### Story Mode:PAMA (1302 words)
```
Not to be confused with M.A.R.I.L.L.A. .
Details
Gender: None
Species: Computer
Status: Destroyed
Aliases: Monster Machine (Petra)​ [ determinant ] A Thinking Machine
Allies: See § Allies
Enemies: See § Enemies
First appearance: Access Denied
Latest appearance: Access Denied
... (81 lines total)
```

---
## 5. VACIOS Y <10 WORDS (106 articles) - Propuesta: ELIMINAR

- **Redstone circuits/Clock/Simple 1-tick piston clock** (0 words): ``
- **Redstone circuits/Clock/Torch rapid pulsers** (2 words): `Rapid Pulser`
- **User:Mcnchsschl/Mob spawning on certain blocks** (0 words): ``
- **Shipwreck/Structure/Upside down back half** (7 words): `The structure is called "upsidedown_backhalf." Layer 1`
- **Bedrock Edition block render history/Camera** (6 words): `Pocket Edition v0.16.0 alpha build 2`
- **Redstone circuits/Piston/Double Extender 4** (6 words): `Design C Design B Design A`
- **Redstone circuits/Clock/Minimal piston clock** (4 words): `Extendible Basic Piston Clock`
- **Tutorial:Piston uses/Full Jeb door** (8 words): `Level 1 Level 2 Level 3 Level 4`
- **Tutorial:Arithmetic logic/Gray code logic unit** (0 words): ``
- **Tutorial:Mining/Per-chunk mine** (0 words): ``

---
## 6. CATEGORY/USER PAGES (28 articles) - Propuesta: ELIMINAR

- **Category:Blocks** (8 words): `A list of all blocks in Minecraft .`
- **Category:Commands** (8 words): `This category contains all pages about commands .`
- **Category:Dangerous versions** (14 words): `Versions of the game that have major issues. See {{ Dangerous version }} .`
- **Category:Disambiguation pages** (29 words): `This category contains pages in the mainspace which serve as disambiguation pages , rather than arti`
- **Category:Enchantments** (4 words): `Enchantments in Minecraft .`
- **Category:Gifs** (0 words): ``
- **Category:Icons** (0 words): ``
- **Category:Images** (7 words): `All images found on the Minecraft Wiki.`

---
## 7. DISAMBIGUATION PAGES (558 articles) - Propuesta: MANTENER

Listan variantes de un mismo nombre.

#### Sand (disambiguation) (204 words)
```
This disambiguation page lists articles associated with the same title. If an internal link led you here, you may wish to change the link to
Sand may refer to:
Minecraft
Blocks
Sand , a gravity-affected block found in many Overworld biomes
Red Sand , red variety of sand
Sandstone , a block found under sand and in several desert structures
Red Sandstone , red variety of sandstone
Soul Sand , a block found in the Nether
Suspicious Sand , a block found in desert wells and desert pyramids
... (31 lines total)
```

#### G (46 words)
```
This disambiguation page lists articles associated with the same title. If an internal link led you here, you may wish to change the link to
G may refer to:
A control button in Java Edition
Gamerscores obtained by completing achievements
```

#### Spider (disambiguation) (306 words)
```
This disambiguation page lists articles associated with the same title. If an internal link led you here, you may wish to change the link to
Spider may refer to:
Minecraft
Mobs
Spider – a neutral arthropod (arachnid), which can climb on walls
Cave Spider – a neutral mob found in caves
Spider Jockey – a skeleton riding a spider
Items
Spider Eye
Fermented Spider Eye
... (62 lines total)
```

#### Jockey (disambiguation) (101 words)
```
This disambiguation page lists articles associated with the same title. If an internal link led you here, you may wish to change the link to
Jockey may refer to:
Minecraft
Main article: Jockey
Camel Husk Jockey
Chicken Jockey
Hoglin Jockey
Ravager Jockey
Skeleton Horseman
Spider Jockey
... (28 lines total)
```

#### Accessibility (52 words)
```
This disambiguation page lists articles associated with the same title. If an internal link led you here, you may wish to change the link to
Accessibility may refer to:
Options § Accessibility Settings , a Java Edition option.
Settings § Accessibility , a Bedrock Edition setting.
```

---
## 8. PROBLEMAS DE CALIDAD DEL TEXTO - Propuesta: FIX CON REGEX

### 8a. Espacios antes de puntuacion (65.8% de articulos)

Antes -> Despues:
```
"a player , hisses" -> "a player, hisses"
"Mob Trophy . This" -> "Mob Trophy. This"
```

Ejemplos reales:

**Trophy (April Fools' joke):**
```
se it is an April Fools' joke , and is therefore not in 
```

**Achievement/Legacy Console and New Nintendo 3DS editions:**
```
ges to complete. In Java Edition , a system of advancements
ock through the tutorial worlds , mini games , and its lob
```

**Client.jar:**
```
mes called "client", see Player . For the block in Bedrock
r download, e.g., 1.21.5.jar . The name client.jar is u
 the file. It is located at .minecraft /versions/ vers
```

**JSON:**
```
and / titleraw commands, books , signs , item names, enti
esource pack that define models , colormaps , sound events
 a data pack that define advancements , loot tables , tags , rec
```

### 8b. URLs residuales (182 articulos)

**Java Edition Classic 0.0.13a:**
- `http://www.minecraft.net/play.jsp?name=<username>&id=<the`

**Java Edition Classic 0.0.17a:**
- `http://www.minecraft.net/play.jsp?ip=<ip>&port=<port>`

**Bedrock Edition beta 1.16.200.53:**
- `https://help.minecraft.net/hc/en-us/articles/360052769812`

### 8c. Wiki markup residual (68 articulos)

**Minecraft Wiki:Admin noticeboard:**
- `{{ delete }} , i decided to provide the list here. my apologies if this wasn't the`

**An Ant:**
- `[[ GRID ICONS GPS 2 ZOOM 32 T 0 "Press Play to start" T 1 "" ]]`

**Ancient City/Structure/Blueprints/City Center:**
- `[[[Special:EditPage/Ancient City/Structure/Blueprints/City Center/City_Center_1`
- `[[[Special:EditPage/Ancient City/Structure/Blueprints/City Center/City_Center_2`
- `[[[Special:EditPage/Ancient City/Structure/Blueprints/City Center/City_Center_3`

### 8d. Cite artifacts (58 articulos)

- **Pack.mcmeta:** `...sion, for example value 82 or [82] is equivalent to [82, 0] ...`
- **Commands/data:** `...=item,limit=1,sort=random] Pos[1] To get the item ID of the ...`
- **Commands/execute:** `...less data entity @s ArmorItems[3].id run kill @s ‌ [ Java Ed...`

---
## 9. GALERIA ('as it appears in...') - Propuesta: MANTENER

**Java Edition Alpha v1.2.2:**
- `pack.png as it appears in this version.`

**15 Year Journey:**
- `Minecraft Classic's title screen, as it appears in the map.`

**Minecraft in popular culture:**
- `A creeper as it appears in the game`
- `The creeper face as it appears in the game`
- `The room as it appears in the game`

---
## 10. CHANGELOGS - Propuesta: MANTENER TODOS

### Java Edition 1.21.11 Release Candidate 1 (308 words)
Player-facing: 308 words | Technical: 0 words
```
Edition: Java Edition
Release date: December 4, 2025
Type: Release Candidate
Release Candidate for: 1.21.11
Downloads: Client Obfuscated ( .json ) Unobfuscated ( .zip ) Server Obfuscated Unobfuscated
Obfuscation maps: Client Server
Protocol version: dec : 1073742108 hex : 4000011C
Data version: 4668
Resource pack format: 75.0
Data pack format: 94.1
Minimum Java version: Java SE 21
Cache ID: Unspecified
...
```

### Java Edition 20w15a (1578 words)
Player-facing: 1069 words | Technical: 0 words
```
Edition: Java Edition
Release date: April 8, 2020
Type: Snapshot
Snapshot for: 1.16
Downloads: Client ( .json ) Server
Obfuscation maps: Client Server
Protocol version: 711
Data version: 2525
Resource pack format: 5
Data pack format: 5
Minimum Java version: Java SE 8
◄ ◄  1.15.2 1.16 1.16.1 ► ► ◄  20w14a 20w15a 20w16a ► | ◄ ◄  1.15.2 | 1.16 | 1.16.1 ► ► | ◄  20w14a | 20w15a | 20w16a ►
...
```

### Java Edition 15w49a (2207 words)
Player-facing: 1074 words | Technical: 0 words
```
This page covers a development version that has an issue under certain conditions.
The game crashes if an item stack is depleted.
Edition: Java Edition
Release date: December 2, 2015
Type: Snapshot
Snapshot for: 1.9
Downloads: Client ( .json ) Server ( .exe )
Protocol version: 90
Data version: 151
Resource pack format: 2
Minimum Java version: Java SE 6
◄ ◄  1.8.9 1.9 1.9.1 ► ► ◄  15w47c 15w49a 15w49b ► | ◄ ◄  1.8.9 | 1.9 | 1.9.1 ► ► | ◄  15w47c | 15w49a | 15w49b ►
...
```

---
## 11. CORE MINECRAFT - Ejemplos de articulos buenos

### Movie:Garrett Garrison (3625 words, 0 sounds)
```
For the sub dungeon in Minecraft Dungeons , see MCD:Garrison .
Details
Gender: Male
Species: Human
Status: Alive
Aliases: The Garbage Man Hot Garbage The Trash Bag ( Marlene ) Gar Gar ( Steve )
Titles: Gamer of the Year, 1989
Occupation: eSports athlete ​ [ formerly ] Video game store owner Video game designer
Affiliations: Game Over World Gang Sizzler (investor) World Video Game Championship (contestant)
Residence: Idaho
Allies: Daryl Steve
First appearance: Uproar in Midport Village
Latest appearance: A Minecraft Movie
Actor: Jason Momoa Moana Williams (Young Garrett)
Garrett Garrison , also known by his nickname " The Garbage Man ", is one of the main protagonists in A Minecraft Movie , played by Jason Mo
... (187 lines total)
```

### Breeze (2865 words, 66 sounds)
```
For other uses, see Breeze (disambiguation) .
Not to be confused with Blaze .
Health points: 30 HP × 15
Behavior: Hostile
Mob type: Monster
Attack strength: Wind Charge : Easy and Normal : 1 HP Hard : 1.5 HP × 0.75
Hitbox size: Height: 1.77 blocks Width: 0.6 blocks
Spawn: Trial Chambers : from trial spawners .
A breeze is a hostile mob spawned by certain trial spawners found in trial chambers . It moves via jumping large distances when attacking, a
Spawning
Breezes spawn from trial spawners that generate surrounded by chiseled tuff in trial chambers . These trial spawners only generate in combat
Breezes can spawn only in places with line of sight to the trial spawner that spawns them.
Drops
On death
Java Edition :
... (217 lines total)
```

### Stonecutter (2304 words, 42 sounds)
```
This article is about the currently obtainable block . For the unobtainable block in Bedrock Edition , see Stonecutter (old) . For other use
Renewable: Yes
Stackable: Yes (64)
Tool
Blast resistance: 3.5
Hardness: 3.5
Luminous: No
Transparent: Java Edition : No Bedrock Edition : Yes
Waterloggable: JE : No BE : Yes
Flammable: No
Catches fire from lava: No
Map color: 11 STONE
A stonecutter is a block used to easily craft many stone and copper blocks, and is cheaper than normal crafting for stairs and copper varian
Obtaining
Breaking
... (188 lines total)
```

### Potion of Regeneration (1324 words, 0 sounds)
```
Rarity tier: Common
Consumption time: 32 game ticks (1.6 seconds)
Always consumable: Yes
Renewable: Yes
Stackable: No
A potion of Regeneration is a potion that provides Regeneration when used.
Obtaining
Brewing
Name: Potion of Regeneration, Ingredients: Ghast Tear+Awkward Potion
Name: Potion of Regeneration +, Ingredients: Redstone Dust+Potion of Regeneration
Name: Potion of Regeneration II, Ingredients: Glowstone Dust+Potion of Regeneration
Name: Splash Potion of Regeneration, Ingredients: Gunpowder+Potion of Regeneration
Name: Lingering Potion of Regeneration, Ingredients: Dragon's Breath+Splash Potion of Regeneration
Mob loot
A witch has an 8.5% chance to drop a potion of Regeneration if it dies while drinking the potion.
... (114 lines total)
```

### Bedrock Edition distance effects (8969 words, 0 sounds)
```
This article is about the effects caused by the 32-bit float precision loss. For other uses, see Distance effects .
This feature is exclusive to Bedrock Edition .
As the player travels far from the world's origin in Bedrock Edition , things begin to break or the world starts to behave abnormally and be
There are a few effects that appear at coordinates other than powers of two, which are shaded in blue on this page. Furthermore, the game de
Map of other distance effects (dramatically not to scale). The Corner Slice Lands still have a bedrock ocean, despite the rendering effectiv
General effects
Some effects can occur at any distance but gradually worsen as the coordinates increase. Bedrock Edition uses 32-bit floating points for man
Block rendering errors
Various blocks are rendered as partial blocks, and the game uses 32-bit floating points to calculate the corners. At high coordinates, these
Terrain generation errors
Many mountain biomes gradually stop generating at around X/Z ±2,812,332, replacing by lava lakes. Ancient cities will also be exposed above 
Slow movement becomes impossible
For an entity to move, it advances a certain distance each tick. At slow speeds or high coordinates, the increase in distance per tick is so
There are several ways to slow the player's movement, such as sneaking , status effects , using an item (e.g. drawing back a bow ), or certa
Jitter
... (232 lines total)
```

