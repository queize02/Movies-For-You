const { Client, GatewayIntentBits, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = require('discord.js');
const express = require('express');
const app = express();

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
app.use(express.json());

// Remplace par tes vrais identifiants
const TOKEN = "MTUwNDExMzk2MTk0MjEyMjQ5Ng.G71vTM.E04sBqcAJlHwqTvYj-p_h7i7lexmrIuAUQTkgY"; 
const CHANNEL_ID = "ID_DU_SALON_DISCORD_ICI";

app.post('/nouvelle-suggestion', async (req, res) => {
    const { titre, user, affiche, film_id } = req.body;
    const channel = await client.channels.fetch(CHANNEL_ID);

    const embed = new EmbedBuilder()
        .setTitle('💡 Nouvelle suggestion')
        .setDescription(`Film : **${titre}**\nProposé par : **${user}**`)
        .setThumbnail(affiche)
        .setColor(0x00FF00);

    const row = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
            .setLabel('🔗 Ajouter le lien')
            .setStyle(ButtonStyle.Link)
            .setURL(`https://movies-for-you.onrender.com/admin/approve_form/${film_id}`)
    );

    await channel.send({ embeds: [embed], components: [row] });
    res.status(200).send("Envoyé");
});

client.login(TOKEN);
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Bot actif sur le port ${PORT}`));