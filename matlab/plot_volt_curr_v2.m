% etime(datevec(data2.Position(1)),datevec(data1.Position(1)))

%% Read data from log file
clear all;
cycle_num = 1;
a = importdata('2014-02-17_2352_lab_power.csv', ',', 1);

date_str = a.textdata(2:end,1);
time_str = a.textdata(2:end,2);
delta_t = a.data(:,1);
volt = a.data(:,2);
curr = a.data(:,3);

%% Convert string dates to Matlab datenum format
% Convert cells to array and concatenate them
date_and_time_str = strcat(cell2mat(date_str), cell2mat(time_str));

% Convert str to Matlab datenum
datenums = datenum(date_and_time_str,'yyyy-mm-ddHH:MM:SS');

%% Find the discharge periods
di = diff(curr);
cap_ind = find(di > 0.2);

for j=1:cycle_num,
   cap_ind(j,2) = cap_ind(j,1) + find(di(cap_ind(j,1):end) > 0.2, 1, 'first');
end

%% Calculate capacity
% Componentwise multiplication between delta_t and current. Lastly, a 
% cumulative sum of the previous vector.
cum_mAh = cumsum( delta_t/1000.*curr/3.6 );

% Calculate individual discharge cycle capacities
for j=1:cycle_num, 
    discharge_capacity(j) = cum_mAh(cap_ind(j,1)) - cum_mAh(cap_ind(j,2));
end

%% Plot for voltage
figure; 
ha(1) = subplot(3,1,1); plot(datenums, volt, 'Color', 'blue', 'LineWidth', 2);
datetick('x');
%ylim([7.8 8.5]);
title('A123 LiFePo (3.3 V 2500 mAh 25560) discharge tests (2*C C C/2 C/5 C/10)','FontSize',14,'FontWeight','bold');
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
plot(datenums, cum_mAh, 'Color', 'green', 'LineWidth', 2); % current data
plot([datenums(1) datenums(end)], [0 0], 'Color', 'black', 'LineWidth', 1, 'LineStyle', '-.'); % zero marker


scatter(datenums(cap_ind(:,1)), cum_mAh(cap_ind(:,1)), 120, 'd', 'k')
scatter(datenums(cap_ind(:,2)), cum_mAh(cap_ind(:,2)), 120, 'd', 'k')

for j=1:cycle_num,
    text(datenums(cap_ind(j,1)),cum_mAh(cap_ind(j,1))+160,[num2str(cum_mAh(cap_ind(j,1)),'%5.0f')],'VerticalAlignment','middle','HorizontalAlignment','left','FontSize',10)
    text(datenums(cap_ind(j,2)),cum_mAh(cap_ind(j,2))-150,[num2str(cum_mAh(cap_ind(j,2)),'%5.0f')],'VerticalAlignment','middle','HorizontalAlignment','left','FontSize',10)
    text(datenums(cap_ind(j,1)),cum_mAh(cap_ind(j,2))-400,[num2str(discharge_capacity(j),'%5.0f'),' mAh'],'VerticalAlignment','middle','FontWeight','bold','HorizontalAlignment','left','FontSize',12)
end

datetick('x','HH:MM');
xlabel('Time','FontSize',12,'FontWeight','bold');
ylabel('Capacity [mAh]','FontSize',12,'FontWeight','bold');
grid on;

%% Additional plot commands
zoomAdaptiveDateTicks('on');
linkaxes(ha, 'x');      % Link all axes in x


%% testing for cap-volt plots
figure('Position',[100 100 1200 800]); hold on;
set(gca,'ytick',linspace(2,4,21));

colors = ['r','g','b','k','y'];
colors2 = [[1 0.1 0.1]; [0.85 0 0]; [0.6 0 0]; [0.45 0.1 0.1]; [0 0 0]];
for j=1:cycle_num,
    vcap_mah = -cum_mAh(cap_ind(j,1):cap_ind(j,2)) + cum_mAh(cap_ind(j,1));
    vcap_volt = volt(cap_ind(j,1):cap_ind(j,2));
    plot(vcap_mah, vcap_volt, 'LineWidth', 2, 'Color', colors2(j,:)); 
end

title('A123 Systems ANR26650 LiFePo cell discharge rate','FontSize',14,'FontWeight','bold');
xlabel('Capacity [mAh]','FontSize',12,'FontWeight','bold');
ylabel('Voltage [V]','FontSize',12,'FontWeight','bold');
hleg = legend('5 A','2.5 A','1.25 A','0.5 A','0.25 A');
set(hleg,'FontSize',12, 'Location', 'SouthWest');
grid on;
ylim([2 3.5]);
xlim([0 2200]);

%% Impedance calculations
total_cap = 2100;
stepsize = 3;

mean_volt = 0;
mean_volts = zeros(cycle_num, 1+total_cap/stepsize);

mean_mah = 0:stepsize:total_cap;

for j=1:cycle_num,
    vcap_mah = -cum_mAh(cap_ind(j,1):cap_ind(j,2)) + cum_mAh(cap_ind(j,1));
    vcap_volt = volt(cap_ind(j,1):cap_ind(j,2));
    
    for range=0:stepsize:total_cap,
        mean_volt = mean(vcap_volt(find(vcap_mah > (range-stepsize/2) & vcap_mah < (range+stepsize/2))));
        mean_volts(j,(range/stepsize)+1) = mean_volt;
    end
end

impedance = zeros(cycle_num-2, 1+total_cap/stepsize);
currents_used = [5 2.5 1.25 0.5 0.25];

for j=1:cycle_num-2,
    for k=1:total_cap/stepsize,
        volt_difference = mean_volts(j+1,:) - mean_volts(j,:);
        curr_difference = currents_used(j) - currents_used(j+1);
        impedance(j,:) = 1000*volt_difference/curr_difference;
    end
end

% multiple axes http://stackoverflow.com/questions/1719048/plotting-4-curves-in-a-single-plot-with-3-y-axes
figure('Position',[100 100 1200 800]);
ax1 = gca;
get(ax1,'Position')
set(ax1,'XColor','k','YColor','k');
set(gca,'ytick',linspace(2,4,21));
hold on;
for j=1:cycle_num,
    line(mean_mah, mean_volts(j,:), 'LineWidth', 2, 'Color', colors2(j,:),'Parent',ax1)
end

title('A123 Systems ANR26650 LiFePo cell discharge rate','FontSize',14,'FontWeight','bold');
xlabel('Capacity [mAh]','FontSize',12,'FontWeight','bold');
ylabel('Voltage [V]','FontSize',12,'FontWeight','bold');
hleg = legend('5 A','2.5 A','1.25 A','0.5 A','0.25 A');
set(hleg,'FontSize',12, 'Location', 'West');
grid on;
ylim([2 3.5]);
xlim([0 2200]);

ax2 = axes('Position',get(ax1,'Position'),...
           'XAxisLocation','bottom',...
           'YAxisLocation','right',...
           'Color','none',...
           'XColor','k',...
           'YColor',[0.5 0.5 0.5],...
           'YLim',[0,200],...
           'XTick',[],'XTickLabel',[]);

line(mean_mah, mean(impedance),'LineWidth', 2, 'Color', [0.6 0.6 0.6], 'Parent', ax2)
ylabel('Resistance [mOhm]','FontSize',12,'FontWeight','bold');
xlim([0 2200]);
