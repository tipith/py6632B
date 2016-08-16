% etime(datevec(data2.Position(1)),datevec(data1.Position(1)))

%% Read data from log file
clear all;
a = importdata('2014-02-05_2105_lab_power.csv', ',', 1);

volt = a.data(:,1);
curr = a.data(:,2);
time = a.textdata(2:end,1);

%% Convert string dates to Matlab datenum format
% 2) convert cell to mat
time_new = cell2mat(time);

% 3) convert to datenum here
datenums = datenum(time_new,'HH:MM:SS');

% day rolling around bug (not needed in new versions)
[minval,ind] = min(datenums);
datenums(ind:end) = datenums(ind:end) + datenum(1);

% calculate capacity: componentwise multiplication between time diff and
% current. and a cumulative sum of that mAh difference vector
cum_mAh = cumsum(etime(datevec(datenums(2:end)),datevec(datenums(1:end-1))).*curr(1:end-1)/3.6);

[max_mah,max_ind] = max(cum_mAh);
[min_mah,min_ind] = min(cum_mAh);

%% Plot for voltage
figure; 
ha(1) = subplot(3,1,1); plot(datenums, volt, 'Color', 'blue', 'LineWidth', 2);
datetick('x');
%ylim([7.8 8.5]);
title('2S2P lithium-ion from DX, test cycle with C/5 discharge','FontSize',14,'FontWeight','bold');
xlabel('Time','FontSize',12,'FontWeight','bold');
ylabel('Voltage [V]','FontSize',12,'FontWeight','bold');
grid on;

%% Plot for current
ha(2) = subplot(3,1,2); hold on; 
plot(datenums, curr, 'Color', 'red', 'LineWidth', 2); % current data
plot([datenums(1) datenums(end)], [0 0], 'Color', 'black', 'LineWidth', 1, 'LineStyle', '-.'); % zero marker
datetick('x');
xlabel('Time','FontSize',12,'FontWeight','bold');
ylabel('Current [A]','FontSize',12,'FontWeight','bold');
grid on;

%% Plot for capacity
ha(3) = subplot(3,1,3); hold on; 
plot(datenums(1:end-1), cum_mAh, 'Color', 'green', 'LineWidth', 2); % current data
plot([datenums(1) datenums(end)], [0 0], 'Color', 'black', 'LineWidth', 1, 'LineStyle', '-.'); % zero marker

scatter([datenums(max_ind) datenums(min_ind)], [max_mah min_mah], 120, 'd', 'k')
text(datenums(max_ind),max_mah+150,...
    [' Max = ',num2str(max_mah,'%5.0f')],...
	'VerticalAlignment','middle',...
	'HorizontalAlignment','left',...
	'FontSize',12)
text(datenums(min_ind),min_mah-150,...
    [' Min = ',num2str(min_mah,'%5.0f')],...
	'VerticalAlignment','middle',...
	'HorizontalAlignment','left',...
	'FontSize',12)
text(datenums(max_ind),-1500,...
    [' Capacity = ',num2str(max_mah-min_mah,'%5.0f'),' mAh'],...
	'VerticalAlignment','middle',...
	'HorizontalAlignment','left',...
	'FontSize',14)

datetick('x');
xlabel('Time','FontSize',12,'FontWeight','bold');
ylabel('Capacity [mAh]','FontSize',12,'FontWeight','bold');
grid on;

%% Additional plot commands
linkaxes(ha, 'x');      % Link all axes in x